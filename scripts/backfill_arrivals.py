"""One-off (Phase 2.5, E1): fill arrivals_tonnes for rows ingested before migration 004.

Arrivals come from the same Agmarknet 2.0 responses as the prices: the cached monthly
files (data/cache/agmarknet_v2/monthly, all of 2018-01..) plus a refetch of months that are
not final yet. Each DB row gets the arrivals of the report it was built from, matched
EXACTLY on (date, market, commodity, variety, modal, min, max) — never by key alone, since
same-day duplicate reports (grades) carry different arrivals.

    uv run python scripts/backfill_arrivals.py --build   # -> data/archive/arrivals_*.parquet
    uv run python scripts/backfill_arrivals.py --apply   # UPDATE NULL arrivals in the DB

Only NULL arrivals are touched; prices are never modified.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, text

from cropcast import db
from cropcast.archive import MATCH_KEY
from cropcast.config import settings
from cropcast.ingest.agmarknet import (
    fetch_portal_month,
    parse_portal_daily,
    parse_portal_month,
    today_ist,
)
from cropcast.ingest.mappings import normalize
from cropcast.logging_setup import setup_logging

log = logging.getLogger("cropcast.backfill_arrivals")

OUT = settings.data_dir / "archive" / "arrivals_from_cache.parquet"


def build() -> pd.DataFrame:
    names = {cid: name for name, cid in settings.agmarknet_commodity_ids.items()}
    frames = []
    monthly = settings.cache_dir / "agmarknet_v2" / "monthly"
    current = pd.Period(today_ist(), "M")
    months = sorted({p.stem for p in monthly.glob("*/*.json")})
    for cid, name in names.items():
        for month in months:
            per = pd.Period(month, "M")
            # Cached final months are read from disk; the current month is refetched.
            payload = fetch_portal_month(per.year, per.month, cid)
            frames.append(parse_portal_month(payload, name))
        if current.strftime("%Y-%m") not in months:
            frames.append(
                parse_portal_month(fetch_portal_month(current.year, current.month, cid), name)
            )
    for f in sorted((settings.cache_dir / "agmarknet_v2" / "daily").glob("*.json")):
        import json

        day = pd.Timestamp(f.stem).date()
        frames.append(parse_portal_daily(json.loads(f.read_text(encoding="utf-8")), day))
    raw = pd.concat(frames, ignore_index=True)
    norm = normalize(raw).dropna(subset=["arrivals_tonnes"])
    out = norm.loc[:, [*MATCH_KEY, "arrivals_tonnes"]].drop_duplicates(
        subset=MATCH_KEY, keep="first"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    log.info("arrivals table built", extra={"rows": len(out), "path": str(OUT)})
    return out


def apply(engine: Engine, arrivals: pd.DataFrame) -> dict[str, int]:
    """UPDATE rows with NULL arrivals in prices_raw and prices_rejected by exact match."""
    a = arrivals.copy()
    a["date"] = pd.to_datetime(a["date"]).dt.date
    counts: dict[str, int] = {}
    with engine.begin() as conn:
        lo = conn.execute(text("SELECT min(date) FROM prices_raw")).scalar()
        if lo is not None:
            a = a[
                a["date"]
                >= min(
                    lo, conn.execute(text("SELECT min(date) FROM prices_rejected")).scalar() or lo
                )
            ]
        conn.execute(
            text(
                "CREATE TEMP TABLE tmp_arrivals (date DATE, market TEXT, commodity TEXT, "
                "variety TEXT, modal_price NUMERIC(12,2), min_price NUMERIC(12,2), "
                "max_price NUMERIC(12,2), arrivals_tonnes NUMERIC(12,3)) ON COMMIT DROP"
            )
        )
        raw_conn = conn.connection.dbapi_connection
        cur = raw_conn.cursor()  # type: ignore[union-attr]
        cols = [*MATCH_KEY, "arrivals_tonnes"]
        with cur.copy(f"COPY tmp_arrivals ({', '.join(cols)}) FROM STDIN") as cp:
            for rec in a.loc[:, cols].itertuples(index=False):
                cp.write_row([None if pd.isna(v) else v for v in rec])
        conn.execute(text("CREATE INDEX ON tmp_arrivals (date, market, commodity, variety)"))
        conn.execute(text("ANALYZE tmp_arrivals"))
        for table in ("prices_raw", "prices_rejected"):
            counts[table] = conn.execute(
                text(
                    f"""
                    UPDATE {table} t SET arrivals_tonnes = s.arrivals_tonnes
                    FROM (SELECT DISTINCT ON (date, market, commodity, variety, modal_price,
                                              min_price, max_price) *
                          FROM tmp_arrivals) s
                    WHERE t.arrivals_tonnes IS NULL
                      AND t.date = s.date AND t.market = s.market AND t.commodity = s.commodity
                      AND t.variety = s.variety AND t.modal_price = s.modal_price
                      AND t.min_price IS NOT DISTINCT FROM s.min_price
                      AND t.max_price IS NOT DISTINCT FROM s.max_price
                    """
                )
            ).rowcount
            counts[f"{table}_still_null"] = int(
                conn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE arrivals_tonnes IS NULL")
                ).scalar_one()
            )
    log.info("arrivals applied", extra=counts)
    return counts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--build", action="store_true")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args(argv)
    setup_logging()
    if args.build:
        build()
    if args.apply:
        engine = db.get_engine()
        db.init_db(engine)
        apply(engine, pd.read_parquet(Path(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
