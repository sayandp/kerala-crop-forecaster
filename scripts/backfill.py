"""One-time historical backfill of Kerala prices into prices_raw.

Source (a), default: Agmarknet 2.0 report API, "Date-wise prices for specified commodity"
(one request per commodity x month, all Kerala markets). History is available from 2018.
Source (b): a local file via --input (CSV or parquet), see `load_input_file` for the format.

Both go through the SAME normalize -> validate -> quarantine -> upsert path as the daily
pipeline. Polite: rate-limited (settings.request_delay_s between calls), every response is
cached under data/cache/agmarknet_v2/monthly/, and progress is checkpointed per
commodity-month in data/cache/backfill_state.json so an interrupted run resumes.

    uv run python scripts/backfill.py --start 2018-01 --end 2026-10
    uv run python scripts/backfill.py --input data/raw/backfill/kerala.csv
    uv run python scripts/backfill.py --weather --start 2018-01   # also weather_daily
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from cropcast import db
from cropcast.config import settings
from cropcast.ingest.agmarknet import (
    fetch_portal_month,
    norm_key,
    parse_portal_month,
    portal_client,
    today_ist,
)
from cropcast.ingest.mappings import normalize
from cropcast.ingest.weather import fetch_weather
from cropcast.logging_setup import setup_logging
from cropcast.pipeline import git_sha
from cropcast.validate.schemas import RejectRateExceeded, check_reject_rate, validate

log = logging.getLogger("cropcast.backfill")

STATE_FILE = settings.cache_dir / "backfill_state.json"
INPUT_ALIASES = {"arrival_date": "date", "price_date": "date", "market_name": "market"}
REQUIRED_INPUT = ["date", "market", "commodity", "variety", "min_price", "max_price", "modal_price"]


def _months(start: str, end: str) -> list[pd.Period]:
    return list(pd.period_range(pd.Period(start, "M"), pd.Period(end, "M"), freq="M"))


def _load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        state: dict[str, Any] = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return state
    return {"done": []}


def _save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def load_batch(raw: pd.DataFrame, run_id: int | None, dry_run: bool) -> dict[str, int]:
    """normalize -> validate -> quarantine -> upsert. Raises RejectRateExceeded."""
    prices = normalize(raw)
    good, rejected = validate(prices)
    if not dry_run:
        db.insert_rejected(rejected, run_id)
    check_reject_rate(len(prices), len(rejected))
    if not dry_run:
        db.upsert_prices(good)
    return {"raw": len(raw), "target": len(prices), "good": len(good), "rejected": len(rejected)}


def backfill_portal(
    months: list[pd.Period],
    commodities: dict[str, int],
    run_id: int | None,
    dry_run: bool,
    force: bool,
) -> tuple[dict[str, int], list[str]]:
    state = _load_state()
    done: set[str] = set(state["done"])
    totals = {"raw": 0, "target": 0, "good": 0, "rejected": 0}
    failures: list[str] = []
    current = pd.Period(today_ist(), "M")
    with portal_client() as client:
        for month in months:
            frames: list[pd.DataFrame] = []
            keys: list[str] = []
            for name, cid in commodities.items():
                key = f"{cid}:{month}"
                # The current month is never "done": it is still filling in.
                if key in done and not force and month < current:
                    continue
                try:
                    payload = fetch_portal_month(month.year, month.month, cid, client)
                except Exception as exc:  # record and keep going
                    log.error(
                        "fetch failed",
                        extra={"commodity": name, "month": str(month), "error": repr(exc)},
                    )
                    failures.append(f"{name} {month}: {exc!r}")
                    continue
                frames.append(parse_portal_month(payload, name))
                keys.append(key)
            if not frames:
                continue
            raw = pd.concat(frames, ignore_index=True)
            try:
                stats = load_batch(raw, run_id, dry_run)
            except RejectRateExceeded as exc:
                log.error("month rejected", extra={"month": str(month), "error": str(exc)})
                failures.append(f"{month}: {exc}")
                continue
            for k, v in stats.items():
                totals[k] += v
            log.info("month loaded", extra={"month": str(month), **stats})
            if not dry_run:
                done.update(keys)
                state["done"] = sorted(done)
                _save_state(state)
    return totals, failures


def load_input_file(path: Path) -> pd.DataFrame:
    """Read a user-supplied history file into the raw standard frame.

    Expected: one row per (date, market, commodity, variety) with columns
      date        ISO yyyy-mm-dd or dd/mm/yyyy   (alias: arrival_date, Arrival_Date)
      state       optional; if present only Kerala/Keralam rows are kept
      district    optional
      market, commodity, variety                (raw Agmarknet names are fine)
      min_price, max_price, modal_price         Rs./quintal
    Column names are case-insensitive; data.gov.in style keys (Modal_x0020_Price) work.
    """
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix.lower() in {".csv", ".gz"}:
        df = pd.read_csv(path, dtype=str)
    else:
        raise ValueError(f"unsupported input type {path.suffix}; use .csv or .parquet")
    df = df.rename(columns=lambda c: norm_key(str(c))).rename(columns=INPUT_ALIASES)
    missing = [c for c in REQUIRED_INPUT if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} is missing columns {missing}; have {list(df.columns)}")
    if "state" in df.columns:
        df = df.loc[df["state"].astype(str).str.strip().str.casefold().isin({"kerala", "keralam"})]
    else:
        df["state"] = "Kerala"
    if "district" not in df.columns:
        df["district"] = None
    dates = df["date"].astype(str)
    iso = pd.to_datetime(dates, format="%Y-%m-%d", errors="coerce")
    dmy = pd.to_datetime(dates, format="%d/%m/%Y", errors="coerce")
    df["date"] = iso.fillna(dmy).dt.date
    df["source"] = f"file:{path.name}"
    return df.reset_index(drop=True)


def backfill_file(
    path: Path, run_id: int | None, dry_run: bool
) -> tuple[dict[str, int], list[str]]:
    df = load_input_file(path)
    totals = {"raw": 0, "target": 0, "good": 0, "rejected": 0}
    failures: list[str] = []
    month = pd.to_datetime(df["date"], errors="coerce").dt.to_period("M")
    for m, chunk in df.groupby(month, dropna=False):
        try:
            stats = load_batch(chunk, run_id, dry_run)
        except RejectRateExceeded as exc:
            failures.append(f"{m}: {exc}")
            continue
        for k, v in stats.items():
            totals[k] += v
        log.info("month loaded", extra={"month": str(m), **stats})
    return totals, failures


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Backfill historical Kerala prices into prices_raw")
    p.add_argument("--start", default="2018-01", help="first month YYYY-MM")
    p.add_argument("--end", default=str(pd.Period(today_ist(), "M")), help="last month YYYY-MM")
    p.add_argument("--commodities", default="all", help="comma list of Agmarknet names or 'all'")
    p.add_argument("--input", type=Path, help="load a CSV/parquet file instead of the portal")
    p.add_argument("--weather", action="store_true", help="also backfill weather_daily")
    p.add_argument("--force", action="store_true", help="ignore checkpoints, re-load all months")
    p.add_argument("--dry-run", action="store_true", help="fetch + validate, no DB writes")
    args = p.parse_args(argv)

    setup_logging(log_file=settings.logs_dir / f"backfill_{today_ist().isoformat()}.jsonl")
    run_id = None
    if not args.dry_run:
        db.init_db()
        run_id = db.start_run(today_ist(), ["backfill"], False, git_sha())

    try:
        if args.input:
            totals, failures = backfill_file(args.input, run_id, args.dry_run)
        else:
            ids = settings.agmarknet_commodity_ids
            if args.commodities != "all":
                wanted = [c.strip() for c in args.commodities.split(",")]
                unknown = [c for c in wanted if c not in ids]
                if unknown:
                    p.error(f"unknown commodities {unknown}; choose from {list(ids)}")
                ids = {c: ids[c] for c in wanted}
            totals, failures = backfill_portal(
                _months(args.start, args.end), ids, run_id, args.dry_run, args.force
            )
        if args.weather:
            start = pd.Period(args.start, "M").start_time.date()
            weather = fetch_weather(start, min(today_ist(), date.today()))
            if not args.dry_run:
                db.upsert_weather(weather)
            totals["weather_rows"] = len(weather)
    except Exception as exc:
        log.exception("backfill crashed")
        if run_id is not None:
            db.finish_run(run_id, "failed", error=repr(exc))
        return 1

    log.info("backfill finished", extra={**totals, "failures": len(failures)})
    for f in failures:
        log.warning("backfill failure", extra={"detail": f})
    if run_id is not None:
        status = "failed" if failures else "success"
        error = "\n".join(failures)[:5000] if failures else None
        db.finish_run(run_id, status, error=error, details={"backfill": totals})
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
