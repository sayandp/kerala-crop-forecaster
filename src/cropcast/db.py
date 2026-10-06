"""Database helpers: engine factory, schema init, idempotent upserts, run log."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import date
from functools import lru_cache
from typing import Any

import pandas as pd
from sqlalchemy import Engine, create_engine, text

from cropcast.config import PROJECT_ROOT, settings

log = logging.getLogger(__name__)

SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"

PRICE_COLUMNS: tuple[str, ...] = (
    "date",
    "state",
    "district",
    "market",
    "commodity",
    "variety",
    "min_price",
    "max_price",
    "modal_price",
    "source",
)
PRICE_KEY: tuple[str, ...] = ("date", "market", "commodity", "variety")
WEATHER_COLUMNS: tuple[str, ...] = (
    "date",
    "district",
    "rainfall_mm",
    "temp_max_c",
    "temp_min_c",
    "temp_mean_c",
    "source",
)


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or settings.database_url, pool_pre_ping=True, future=True)


def init_db(engine: Engine | None = None) -> None:
    """Apply sql/schema.sql (all statements are IF NOT EXISTS, so this is idempotent)."""
    engine = engine or get_engine()
    ddl = SCHEMA_PATH.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(ddl)
    log.info("schema applied", extra={"schema": str(SCHEMA_PATH)})


def _records(df: pd.DataFrame, columns: Sequence[str]) -> list[dict[str, Any]]:
    """DataFrame -> list of plain-python dicts with NaN/NaT mapped to None."""
    out = df.loc[:, list(columns)].astype(object)
    out = out.where(pd.notna(out), None)
    recs: list[dict[str, Any]] = out.to_dict(orient="records")  # type: ignore[assignment]
    for r in recs:
        d = r.get("date")
        if isinstance(d, pd.Timestamp):
            r["date"] = d.date()
    return recs


_UPSERT_PRICES_SQL = text(
    """
    INSERT INTO prices_raw (date, state, district, market, commodity, variety,
                            min_price, max_price, modal_price, source)
    VALUES (:date, :state, :district, :market, :commodity, :variety,
            :min_price, :max_price, :modal_price, :source)
    ON CONFLICT (date, market, commodity, variety) DO UPDATE SET
        state       = EXCLUDED.state,
        district    = EXCLUDED.district,
        min_price   = EXCLUDED.min_price,
        max_price   = EXCLUDED.max_price,
        modal_price = EXCLUDED.modal_price,
        source      = EXCLUDED.source,
        updated_at  = now()
    WHERE (prices_raw.state, prices_raw.district, prices_raw.min_price,
           prices_raw.max_price, prices_raw.modal_price, prices_raw.source)
        IS DISTINCT FROM
          (EXCLUDED.state, EXCLUDED.district, EXCLUDED.min_price,
           EXCLUDED.max_price, EXCLUDED.modal_price, EXCLUDED.source)
    """
)


def upsert_prices(df: pd.DataFrame, engine: Engine | None = None) -> int:
    """Idempotently upsert validated price rows into prices_raw. Returns rows sent."""
    if df.empty:
        return 0
    engine = engine or get_engine()
    recs = _records(df, PRICE_COLUMNS)
    with engine.begin() as conn:
        conn.execute(_UPSERT_PRICES_SQL, recs)
    log.info("upserted prices", extra={"rows": len(recs)})
    return len(recs)


def insert_rejected(df: pd.DataFrame, run_id: int | None, engine: Engine | None = None) -> int:
    """Append quarantined rows (with a `reason` column) to prices_rejected."""
    if df.empty:
        return 0
    engine = engine or get_engine()
    frame = df.copy()
    for col in PRICE_COLUMNS:
        if col not in frame.columns:
            frame[col] = None
    # Unparseable values must not break the quarantine insert itself.
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for col in ("min_price", "max_price", "modal_price"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["run_id"] = run_id
    recs = _records(frame, (*PRICE_COLUMNS, "reason", "run_id"))
    stmt = text(
        """
        INSERT INTO prices_rejected (run_id, date, state, district, market, commodity, variety,
                                     min_price, max_price, modal_price, source, reason)
        VALUES (:run_id, :date, :state, :district, :market, :commodity, :variety,
                :min_price, :max_price, :modal_price, :source, :reason)
        """
    )
    with engine.begin() as conn:
        conn.execute(stmt, recs)
    log.warning("quarantined rows", extra={"rows": len(recs)})
    return len(recs)


def upsert_weather(df: pd.DataFrame, engine: Engine | None = None) -> int:
    if df.empty:
        return 0
    engine = engine or get_engine()
    recs = _records(df, WEATHER_COLUMNS)
    stmt = text(
        """
        INSERT INTO weather_daily (date, district, rainfall_mm, temp_max_c, temp_min_c,
                                   temp_mean_c, source)
        VALUES (:date, :district, :rainfall_mm, :temp_max_c, :temp_min_c, :temp_mean_c, :source)
        ON CONFLICT (date, district) DO UPDATE SET
            rainfall_mm = EXCLUDED.rainfall_mm,
            temp_max_c  = EXCLUDED.temp_max_c,
            temp_min_c  = EXCLUDED.temp_min_c,
            temp_mean_c = EXCLUDED.temp_mean_c,
            source      = EXCLUDED.source,
            ingested_at = now()
        """
    )
    with engine.begin() as conn:
        conn.execute(stmt, recs)
    return len(recs)


def database_size_mb(engine: Engine | None = None) -> float:
    """Current database size in MB (free-tier budget: see CLAUDE.md)."""
    engine = engine or get_engine()
    with engine.connect() as conn:
        size = conn.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
    return round(int(size) / 1024 / 1024, 1)


# --- pipeline_runs ----------------------------------------------------------


def start_run(
    run_date: date,
    steps: Sequence[str],
    dry_run: bool,
    git_sha: str | None,
    engine: Engine | None = None,
) -> int:
    engine = engine or get_engine()
    with engine.begin() as conn:
        run_id = conn.execute(
            text(
                """
                INSERT INTO pipeline_runs (run_date, steps, dry_run, status, git_sha)
                VALUES (:run_date, :steps, :dry_run, 'running', :git_sha)
                RETURNING run_id
                """
            ),
            {
                "run_date": run_date,
                "steps": ",".join(steps),
                "dry_run": dry_run,
                "git_sha": git_sha,
            },
        ).scalar_one()
    return int(run_id)


def finish_run(
    run_id: int,
    status: str,
    error: str | None = None,
    details: dict[str, Any] | None = None,
    engine: Engine | None = None,
) -> None:
    engine = engine or get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE pipeline_runs
                SET status = :status, finished_at = now(), error = :error,
                    details = CAST(:details AS JSONB)
                WHERE run_id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "status": status,
                "error": error,
                "details": json.dumps(details or {}, default=str),
            },
        )
