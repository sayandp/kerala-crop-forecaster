"""Daily pipeline orchestrator.

    python -m cropcast.pipeline --steps ingest,validate [--date YYYY-MM-DD] [--dry-run]

Each step is `run_<step>(ctx: RunContext) -> StepResult`, so it can later be wrapped as a
Prefect @task unchanged. Every non-dry run is logged in `pipeline_runs`; any failure marks
the run failed and pings the admin on Telegram.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine, text

from cropcast import db
from cropcast.alerts.admin import send_admin_message
from cropcast.clean.aliases import evaluate_candidates, load_candidates
from cropcast.clean.build import build_clean, eligible_duplicates
from cropcast.config import PROJECT_ROOT, settings
from cropcast.ingest.agmarknet import IST, fetch_kerala_prices, today_ist
from cropcast.ingest.mappings import normalize
from cropcast.ingest.weather import fetch_weather
from cropcast.logging_setup import setup_logging
from cropcast.validate.schemas import check_reject_rate, validate

log = logging.getLogger("cropcast.pipeline")


@dataclass
class RunContext:
    run_date: date
    dry_run: bool = False
    lookback_days: int = field(default_factory=lambda: settings.ingest_lookback_days)
    full: bool = False  # clean: re-evaluate aliases + rebuild prices_clean from scratch
    tune: bool = False  # train: Optuna search before fitting
    run_id: int | None = None
    engine: Engine | None = None
    # Hand-off between steps within one process (e.g. ingest -> validate).
    artifacts: dict[str, Any] = field(default_factory=dict)

    @property
    def window(self) -> tuple[date, date]:
        return self.run_date - timedelta(days=self.lookback_days), self.run_date


@dataclass
class StepResult:
    step: str
    ok: bool = True
    metrics: dict[str, Any] = field(default_factory=dict)


def _snapshot_dir(run_date: date) -> Path:
    return settings.raw_dir / "prices" / f"run_date={run_date.isoformat()}"


# --- steps --------------------------------------------------------------------


def run_ingest(ctx: RunContext) -> StepResult:
    """Fetch Kerala prices for the lookback window, normalize, snapshot to data/raw/."""
    raw = fetch_kerala_prices(ctx.run_date, ctx.lookback_days)
    prices = normalize(raw)
    ctx.artifacts["prices"] = prices
    metrics: dict[str, Any] = {"raw_rows": len(raw), "target_rows": len(prices)}
    if not ctx.dry_run:
        # Immutable snapshot: a new file per ingest, never overwritten.
        out = _snapshot_dir(ctx.run_date) / f"{datetime.now(IST):%Y%m%dT%H%M%S%f}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():  # immutable: never overwrite a snapshot
            raise FileExistsError(out)
        prices.to_parquet(out, index=False)
        metrics["snapshot"] = str(out)
    return StepResult("ingest", metrics=metrics)


def _load_latest_snapshot(run_date: date) -> pd.DataFrame:
    files = sorted(_snapshot_dir(run_date).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no ingest snapshot for {run_date}; run the ingest step first")
    return pd.read_parquet(files[-1])


def _count_prices(engine: Engine, start: date, end: date) -> int:
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM prices_raw WHERE date BETWEEN :s AND :e"),
            {"s": start, "e": end},
        ).scalar_one()
    return int(n)


def run_validate(ctx: RunContext) -> StepResult:
    """Apply the data contract; quarantine bad rows; upsert good rows into prices_raw."""
    prices = ctx.artifacts.get("prices")
    if prices is None:
        prices = _load_latest_snapshot(ctx.run_date)
    good, rejected = validate(prices)
    metrics: dict[str, Any] = {
        "rows": len(prices),
        "good": len(good),
        "rejected": len(rejected),
        "reject_reasons": rejected["reason"].value_counts().to_dict() if len(rejected) else {},
    }
    if ctx.dry_run:
        check_reject_rate(len(prices), len(rejected))
        return StepResult("validate", metrics=metrics)

    engine = ctx.engine or db.get_engine()
    db.insert_rejected(rejected, ctx.run_id, engine)
    # Gate after quarantining (so the bad rows are inspectable) but before loading anything.
    metrics["reject_rate"] = round(check_reject_rate(len(prices), len(rejected)), 4)
    start, end = ctx.window
    before = _count_prices(engine, start, end)
    db.upsert_prices(good, engine)
    after = _count_prices(engine, start, end)
    metrics.update({"upserted": len(good), "new_rows": after - before, "rows_in_window": after})
    per_crop = good.groupby("commodity").size().to_dict() if len(good) else {}
    metrics["good_by_commodity"] = per_crop
    missing = sorted(set(settings.target_commodities) - set(per_crop))
    if missing:
        log.warning("no rows for target commodities in window", extra={"missing": missing})
    return StepResult("validate", metrics=metrics)


def run_weather(ctx: RunContext) -> StepResult:
    """District rainfall/temperature for the lookback window -> weather_daily."""
    start, end = ctx.window
    weather = fetch_weather(start, end)
    if not ctx.dry_run:
        db.upsert_weather(weather, ctx.engine or db.get_engine())
    return StepResult("weather", metrics={"rows": len(weather)})


def run_clean(ctx: RunContext) -> StepResult:
    """prices_raw (+ quarantined same-day duplicates) -> aliases -> aggregated prices_clean."""
    engine = ctx.engine or db.get_engine()
    start = None if ctx.full else ctx.run_date - timedelta(days=settings.clean_window_days)
    metrics: dict[str, Any] = {"mode": "full" if ctx.full else f"since {start}"}

    aliases = db.read_variety_aliases(engine)
    if ctx.full or aliases.empty:
        sw = settings.portal_switch_date
        w = timedelta(days=settings.alias_guard_window_days)
        accepted, decisions = evaluate_candidates(
            db.read_prices_raw(sw - w, sw + w - timedelta(days=1), engine),
            load_candidates(),
            sw,
            settings.alias_guard_tolerance,
            settings.alias_guard_window_days,
            settings.alias_guard_min_obs,
        )
        for d in decisions.to_dict("records"):
            log.info(
                "alias decision",
                extra={
                    "commodity": d["commodity"],
                    "market": d["market"],
                    "rename": f"{d['raw_variety']} -> {d['canonical_variety']}",
                    "n_before": d["n_before"],
                    "n_after": d["n_after"],
                    "ratio": None if pd.isna(d["ratio"]) else round(d["ratio"], 4),
                    "decision": d["decision"],
                },
            )
        if not ctx.dry_run:
            settings.reports_dir.mkdir(parents=True, exist_ok=True)
            decisions.to_csv(settings.reports_dir / "alias_decisions.csv", index=False)
            db.replace_variety_aliases(accepted, engine)
        aliases = accepted
        metrics["alias_candidates"] = len(decisions)
        metrics["aliases_accepted"] = len(accepted)

    raw = db.read_prices_raw(start, None, engine)
    duplicates = eligible_duplicates(db.read_duplicate_rejects(start, engine))
    clean = build_clean(raw, duplicates, aliases)
    metrics.update(
        {
            "raw_rows": len(raw),
            "duplicate_reports": len(duplicates),
            "clean_rows": len(clean),
            "multi_report_days": int((clean["n_reports"] > 1).sum()) if len(clean) else 0,
        }
    )
    if not ctx.dry_run:
        db.replace_prices_clean(clean, start, engine)
    return StepResult("clean", metrics=metrics)


STEPS: dict[str, Callable[[RunContext], StepResult]] = {
    "ingest": run_ingest,
    "validate": run_validate,
    "weather": run_weather,
    "clean": run_clean,
}
ALL_STEPS = list(STEPS)


# --- orchestration --------------------------------------------------------------


def git_sha() -> str | None:
    if sha := os.environ.get("GITHUB_SHA"):
        return sha
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _run_details(ctx: RunContext, results: list[StepResult]) -> dict[str, Any]:
    """Per-step metrics plus db_size_mb (best effort: a DB error must not mask the run's)."""
    details: dict[str, Any] = {r.step: r.metrics for r in results}
    try:
        details["db_size_mb"] = db.database_size_mb(ctx.engine)
    except Exception:
        log.warning("could not measure db size", exc_info=True)
        details["db_size_mb"] = None
    ctx.artifacts["details"] = details
    return details


def _check_db_budget(size_mb: float | None) -> None:
    if size_mb is None or size_mb < settings.db_warn_mb:
        return
    log.warning(
        "database size near free-tier limit",
        extra={"db_size_mb": size_mb, "budget_mb": settings.db_budget_mb},
    )
    send_admin_message(
        f"cropcast DB is {size_mb:.0f} MB (warn {settings.db_warn_mb:.0f}, "
        f"budget {settings.db_budget_mb:.0f}, Neon free tier 512). Prune before it fills."
    )


def run_pipeline(steps: list[str], ctx: RunContext) -> list[StepResult]:
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        raise ValueError(f"unknown steps {unknown}; choose from {ALL_STEPS}")

    results: list[StepResult] = []
    current = "setup"
    try:
        if not ctx.dry_run:
            ctx.engine = ctx.engine or db.get_engine()
            db.init_db(ctx.engine)
            ctx.run_id = db.start_run(ctx.run_date, steps, ctx.dry_run, git_sha(), ctx.engine)
        log.info(
            "pipeline started",
            extra={
                "run_id": ctx.run_id,
                "run_date": str(ctx.run_date),
                "steps": steps,
                "dry_run": ctx.dry_run,
            },
        )
        for current in steps:
            result = STEPS[current](ctx)
            results.append(result)
            log.info("step finished", extra={"step": current, **result.metrics})
    except Exception as exc:
        log.exception("step failed", extra={"step": current})
        error = f"{current}: {type(exc).__name__}: {exc}"
        if ctx.run_id is not None:
            db.finish_run(
                ctx.run_id,
                "failed",
                error=error + "\n" + traceback.format_exc(limit=5),
                details={r.step: r.metrics for r in results},
                engine=ctx.engine,
            )
        send_admin_message(
            f"cropcast pipeline FAILED ({settings.env})\n"
            f"run_id={ctx.run_id} date={ctx.run_date} step={current}\n{error}"
        )
        raise
    if ctx.run_id is not None:
        details = _run_details(ctx, results)
        db.finish_run(ctx.run_id, "success", details=details, engine=ctx.engine)
        _check_db_budget(details["db_size_mb"])
    size = ctx.artifacts.get("details", {}).get("db_size_mb")
    log.info("pipeline finished", extra={"run_id": ctx.run_id, "db_size_mb": size})
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="cropcast.pipeline", description=__doc__.split("\n\n")[0])
    p.add_argument("--steps", default="ingest,validate", help=f"comma list of {ALL_STEPS} or 'all'")
    p.add_argument(
        "--date", type=date.fromisoformat, default=None, help="run date (IST); default today"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="fetch + validate only; no DB/disk writes"
    )
    p.add_argument(
        "--lookback",
        type=int,
        default=settings.ingest_lookback_days,
        help="also re-pull this many days before --date (late market reports)",
    )
    p.add_argument(
        "--full", action="store_true", help="clean: re-evaluate aliases and rebuild everything"
    )
    p.add_argument("--tune", action="store_true", help="train: Optuna search (h=7, folds 1-3)")
    p.add_argument(
        "--status-file",
        type=Path,
        default=None,
        help="write a JSON run summary here (CI commits it as status/last_run.json)",
    )
    return p.parse_args(argv)


def write_status(path: Path, ctx: RunContext, steps: list[str], status: str) -> None:
    details: dict[str, Any] = ctx.artifacts.get("details", {})
    payload = {
        "run_date": ctx.run_date.isoformat(),
        "finished_at": datetime.now(IST).isoformat(timespec="seconds"),
        "status": status,
        "run_id": ctx.run_id,
        "steps": steps,
        "dry_run": ctx.dry_run,
        "db_size_mb": details.get("db_size_mb"),
        "rows_upserted": details.get("validate", {}).get("upserted"),
        "rows_new": details.get("validate", {}).get("new_rows"),
        "git_sha": git_sha(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_date: date = args.date or today_ist()
    steps = (
        ALL_STEPS
        if args.steps.strip() == "all"
        else [s.strip() for s in args.steps.split(",") if s.strip()]
    )
    log_file = (
        settings.logs_dir / f"pipeline_{run_date.isoformat()}_{datetime.now(IST):%H%M%S}.jsonl"
    )
    setup_logging(log_file=None if args.dry_run else log_file)
    ctx = RunContext(
        run_date=run_date,
        dry_run=args.dry_run,
        lookback_days=args.lookback,
        full=args.full,
        tune=args.tune,
    )
    status = "failed"
    try:
        run_pipeline(steps, ctx)
        status = "success"
    except Exception:
        return 1
    finally:
        if args.status_file is not None:
            write_status(args.status_file, ctx, steps, status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
