"""Archive old prices_raw rows to GitHub Release assets, then delete them from the DB.

Neon's free tier is 0.5 GB, so prices_raw keeps only the last `archive_after_days` (90) days;
older rows live in yearly parquet files attached to a GitHub Release `data-archive-<date>`.
prices_clean keeps the full history in the DB.

Order (never delete before the copy is proven):
  1. read rows dated < cutoff,  2. write data/archive/<tag>/prices_raw_<year>.parquet,
  3. upload with `gh release create`,  4. download the assets back and compare row counts and
  a modal-price checksum per year with the DB,  5. DELETE (count asserted) + VACUUM FULL,
  6. record the release in archive_log.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, text

from cropcast.config import settings

log = logging.getLogger(__name__)

TAG_PREFIX = "data-archive-"
FILE_GLOB = "prices_raw_*.parquet"


def archive_root() -> Path:
    return settings.data_dir / "archive"


@dataclass(frozen=True)
class ArchiveResult:
    tag: str
    cutoff: date
    rows: int
    files: list[Path]


def _gh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    if shutil.which("gh") is None:
        raise RuntimeError("GitHub CLI `gh` is required for the archive (not found on PATH)")
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check, timeout=600)


def read_rows_before(engine: Engine, cutoff: date) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(
            text(
                "SELECT date, state, district, market, commodity, variety, "
                "min_price::float8 AS min_price, max_price::float8 AS max_price, "
                "modal_price::float8 AS modal_price, arrivals_tonnes::float8 AS arrivals_tonnes, "
                "source, ingested_at, updated_at FROM prices_raw WHERE date < :c "
                "ORDER BY date, market, commodity, variety"
            ),
            conn,
            params={"c": cutoff},
        )


def _per_year(df: pd.DataFrame) -> pd.DataFrame:
    years = pd.to_datetime(df["date"]).dt.year
    return df.groupby(years).agg(rows=("modal_price", "size"), modal_sum=("modal_price", "sum"))


def write_parquet(rows: pd.DataFrame, tag: str) -> list[Path]:
    out = archive_root() / tag
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for year, part in rows.groupby(pd.to_datetime(rows["date"]).dt.year):
        path = out / f"prices_raw_{year}.parquet"
        part.to_parquet(path, index=False)
        paths.append(path)
    return paths


def upload_release(tag: str, files: list[Path], cutoff: date, rows: int) -> None:
    notes = (
        f"prices_raw rows dated before {cutoff} ({rows:,} rows), archived from Neon to stay "
        "within the free tier. Yearly parquet; columns as in sql/schema.sql (prices_raw). "
        "Prices Rs./quintal, arrivals metric tonnes."
    )
    _gh("release", "create", tag, *map(str, files), "--title", tag, "--notes", notes)


def download_release(tag: str, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    _gh("release", "download", tag, "--pattern", FILE_GLOB, "--dir", str(dest), "--clobber")
    return sorted(dest.glob(FILE_GLOB))


def verify_release(tag: str, expected: pd.DataFrame) -> None:
    """Download the release back and compare per-year row counts + modal checksums."""
    with tempfile.TemporaryDirectory() as tmp:
        files = download_release(tag, Path(tmp))
        got = _per_year(pd.concat([pd.read_parquet(f) for f in files], ignore_index=True))
    want = _per_year(expected)
    if (
        not got["rows"].equals(want["rows"])
        or not ((got["modal_sum"] - want["modal_sum"]).abs() < 0.01).all()
    ):
        raise RuntimeError(f"archive verification failed for {tag}:\nDB:\n{want}\nrelease:\n{got}")
    log.info("archive verified", extra={"tag": tag, "per_year_rows": want["rows"].to_dict()})


def delete_and_vacuum(engine: Engine, cutoff: date, expected_rows: int) -> None:
    with engine.begin() as conn:
        deleted = conn.execute(
            text("DELETE FROM prices_raw WHERE date < :c"), {"c": cutoff}
        ).rowcount
        if deleted != expected_rows:
            raise RuntimeError(
                f"expected to delete {expected_rows} rows, got {deleted}: rolled back"
            )
    # VACUUM FULL returns the space to the OS (plain DELETE would leave the table size as is).
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("VACUUM FULL prices_raw"))


def record(engine: Engine, result: ArchiveResult) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO archive_log (release_tag, cutoff_date, rows) "
                "VALUES (:t, :c, :r) ON CONFLICT (release_tag) DO NOTHING"
            ),
            {"t": result.tag, "c": result.cutoff, "r": result.rows},
        )


def archive_prices_raw(
    engine: Engine,
    cutoff: date,
    tag: str,
    enrich: pd.DataFrame | None = None,
    dry_run: bool = False,
) -> ArchiveResult:
    """Archive prices_raw rows dated < cutoff to release `tag`, then delete them."""
    rows = read_rows_before(engine, cutoff)
    if rows.empty:
        log.info("nothing to archive", extra={"cutoff": str(cutoff)})
        return ArchiveResult(tag, cutoff, 0, [])
    if enrich is not None:
        rows = fill_arrivals(rows, enrich)
    files = write_parquet(rows, tag)
    result = ArchiveResult(tag, cutoff, len(rows), files)
    log.info("archive written", extra={"tag": tag, "rows": len(rows), "files": len(files)})
    if dry_run:
        return result
    upload_release(tag, files, cutoff, len(rows))
    verify_release(tag, rows)
    delete_and_vacuum(engine, cutoff, len(rows))
    record(engine, result)
    return result


# --- reading the archive back (clean --full) ---------------------------------------------


def archived_tags(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return [
            r[0]
            for r in conn.execute(text("SELECT release_tag FROM archive_log ORDER BY cutoff_date"))
        ]


def load_archive(engine: Engine) -> pd.DataFrame:
    """All archived prices_raw rows (downloads missing releases into data/archive/<tag>/)."""
    frames: list[pd.DataFrame] = []
    for tag in archived_tags(engine):
        local = archive_root() / tag
        files = sorted(local.glob(FILE_GLOB)) if local.exists() else []
        if not files:
            files = download_release(tag, local)
        frames.extend(pd.read_parquet(f) for f in files)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# --- arrivals enrichment (Phase 2.5 one-off) ----------------------------------------------

MATCH_KEY = ["date", "market", "commodity", "variety", "modal_price", "min_price", "max_price"]


def fill_arrivals(rows: pd.DataFrame, arrivals: pd.DataFrame) -> pd.DataFrame:
    """Fill NULL arrivals by exact match on key + prices (the report that was kept)."""
    a = arrivals.loc[:, [*MATCH_KEY, "arrivals_tonnes"]].copy()
    a["date"] = pd.to_datetime(a["date"]).dt.date
    a = a.drop_duplicates(subset=MATCH_KEY, keep="first")
    r = rows.copy()
    r["date"] = pd.to_datetime(r["date"]).dt.date
    merged = r.merge(a, on=MATCH_KEY, how="left", suffixes=("", "_new"))
    merged["arrivals_tonnes"] = merged["arrivals_tonnes"].fillna(merged.pop("arrivals_tonnes_new"))
    return merged
