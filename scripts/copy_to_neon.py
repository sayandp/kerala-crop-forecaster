"""Copy all public tables from local Postgres to Neon (no pg_dump needed).

Usage (PowerShell):
  $env:LOCAL_DB_URL = "postgresql://cropcast:cropcast@localhost:5432/cropcast"
  $env:NEON_URL     = "postgresql://neondb_owner:...@ep-....neon.tech/neondb?sslmode=require"
  python scripts/copy_to_neon.py            # copies into empty tables, skips non-empty
  python scripts/copy_to_neon.py --truncate # wipe target tables first
"""

import os
import sys
import time
from pathlib import Path

import psycopg
from sqlalchemy import MetaData, create_engine


def raw(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def sa(url: str) -> str:
    return raw(url).replace("postgresql://", "postgresql+psycopg://", 1)


SRC, DST = os.environ["LOCAL_DB_URL"], os.environ["NEON_URL"]
TRUNCATE = "--truncate" in sys.argv

# 1. Table order (parents before children) from the local DB
md = MetaData()
md.reflect(create_engine(sa(SRC)))
tables = md.sorted_tables

with psycopg.connect(raw(SRC)) as src, psycopg.connect(raw(DST)) as dst:
    # 2. Create schema on Neon from the repo's canonical DDL (+ migrations)
    ddl_files = [Path("sql/schema.sql"), *sorted(Path("sql/migrations").glob("*.sql"))]
    for f in ddl_files:
        if not f.exists():
            continue
        try:
            dst.execute(f.read_text(encoding="utf-8"))
            dst.commit()
            print(f"applied {f}")
        except psycopg.Error as e:  # already exists on re-run etc.
            dst.rollback()
            print(f"skipped {f}: {str(e).splitlines()[0]}")

    existing = {
        r[0]
        for r in dst.execute(
            "select table_name from information_schema.tables where table_schema='public'"
        )
    }

    # 3. Stream each table with COPY
    for t in tables:
        name = t.name
        if name not in existing:
            print(f"!! {name} missing on Neon (not in schema.sql) — skipped")
            continue
        n_dst = dst.execute(f'select count(*) from "{name}"').fetchone()[0]
        if n_dst and not TRUNCATE:
            print(f"-- {name}: Neon already has {n_dst} rows, skipped (use --truncate)")
            continue
        if n_dst:
            dst.execute(f'truncate "{name}" cascade')

        cols = ", ".join(f'"{c.name}"' for c in t.columns)
        t0 = time.time()
        with (
            src.cursor().copy(f'COPY "{name}" ({cols}) TO STDOUT') as out,
            dst.cursor().copy(f'COPY "{name}" ({cols}) FROM STDIN') as inp,
        ):
            for chunk in out:
                inp.write(chunk)

        # fix serial/identity sequences
        for c in t.columns:
            seq = dst.execute(
                "select pg_get_serial_sequence(%s, %s)", (f'public."{name}"', c.name)
            ).fetchone()[0]
            if seq:
                max_sql = f'select max("{c.name}") from "{name}"'
                dst.execute(f"select setval(%s, coalesce(({max_sql}), 1))", (seq,))
        dst.commit()

        n_src = src.execute(f'select count(*) from "{name}"').fetchone()[0]
        n_new = dst.execute(f'select count(*) from "{name}"').fetchone()[0]
        flag = "OK" if n_src == n_new else "MISMATCH"
        print(f"{flag} {name}: {n_new}/{n_src} rows in {time.time() - t0:.0f}s")

    size = dst.execute("select pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
    print(f"\nNeon DB size: {size}")
