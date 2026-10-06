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
MIGRATIONS_DIR = PROJECT_ROOT / "sql" / "migrations"

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
    """Apply sql/schema.sql, then every sql/migrations/*.sql in order.

    Everything is idempotent, so this runs on every pipeline run and brings any database
    (local or Neon) up to date without a migrations bookkeeping table.
    """
    engine = engine or get_engine()
    files = [SCHEMA_PATH, *sorted(MIGRATIONS_DIR.glob("*.sql"))]
    with engine.begin() as conn:
        # Raw driver cursor with no parameters: '%' in SQL comments is not a placeholder.
        cur = conn.connection.dbapi_connection.cursor()  # type: ignore[union-attr]
        for f in files:
            cur.execute(f.read_text(encoding="utf-8"))
    log.info("schema applied", extra={"files": [f.name for f in files]})


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


def insert_prices_if_absent(df: pd.DataFrame, engine: Engine | None = None) -> int:
    """Insert price rows whose key is not in prices_raw yet; never touches existing rows."""
    if df.empty:
        return 0
    engine = engine or get_engine()
    stmt = text(
        """
        INSERT INTO prices_raw (date, state, district, market, commodity, variety,
                                min_price, max_price, modal_price, source)
        VALUES (:date, :state, :district, :market, :commodity, :variety,
                :min_price, :max_price, :modal_price, :source)
        ON CONFLICT (date, market, commodity, variety) DO NOTHING
        """
    )
    count = text("SELECT count(*) FROM prices_raw")
    with engine.begin() as conn:
        before = int(conn.execute(count).scalar_one())
        conn.execute(stmt, _records(df, PRICE_COLUMNS))  # one batched executemany
        after = int(conn.execute(count).scalar_one())
    return after - before


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


# --- clean layer ------------------------------------------------------------------


def read_prices_raw(
    start: date | None = None, end: date | None = None, engine: Engine | None = None
) -> pd.DataFrame:
    engine = engine or get_engine()
    sql = (
        "SELECT date, market, commodity, variety, min_price::float8 AS min_price, "
        "max_price::float8 AS max_price, modal_price::float8 AS modal_price, source "
        "FROM prices_raw WHERE date >= COALESCE(:s, DATE '1900-01-01') "
        "AND date <= COALESCE(:e, DATE '2999-12-31')"
    )
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params={"s": start, "e": end})


def read_duplicate_rejects(start: date | None = None, engine: Engine | None = None) -> pd.DataFrame:
    """Quarantined rows that were (at least) same-day duplicates; input to prices_clean."""
    engine = engine or get_engine()
    sql = (
        f"SELECT {', '.join(PRICE_COLUMNS)}, reason FROM prices_rejected "
        "WHERE reason LIKE :pat AND date >= COALESCE(:s, DATE '1900-01-01') ORDER BY id"
    )
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params={"pat": "%duplicate_key%", "s": start})


def read_variety_aliases(engine: Engine | None = None) -> pd.DataFrame:
    engine = engine or get_engine()
    with engine.connect() as conn:
        return pd.read_sql(
            text(
                "SELECT commodity, market, raw_variety, canonical_variety, valid_from, "
                "valid_to, guard_ratio FROM variety_aliases ORDER BY id"
            ),
            conn,
        )


def replace_variety_aliases(aliases: pd.DataFrame, engine: Engine | None = None) -> int:
    engine = engine or get_engine()
    cols = ("commodity", "market", "raw_variety", "canonical_variety", "valid_from", "valid_to")
    stmt = text(
        "INSERT INTO variety_aliases (commodity, market, raw_variety, canonical_variety, "
        "valid_from, valid_to, guard_ratio) VALUES (:commodity, :market, :raw_variety, "
        ":canonical_variety, :valid_from, :valid_to, :guard_ratio)"
    )
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM variety_aliases"))
        if not aliases.empty:
            conn.execute(stmt, _records_any(aliases, (*cols, "guard_ratio")))
    return len(aliases)


def replace_prices_clean(
    clean: pd.DataFrame, start: date | None, engine: Engine | None = None
) -> int:
    """Replace prices_clean rows dated >= start (all rows when start is None)."""
    engine = engine or get_engine()
    cols = (
        "commodity",
        "market",
        "variety",
        "date",
        "modal_price",
        "min_price",
        "max_price",
        "n_reports",
        "sources",
    )
    stmt = text(
        "INSERT INTO prices_clean (commodity, market, variety, date, modal_price, min_price, "
        "max_price, n_reports, sources) VALUES (:commodity, :market, :variety, :date, "
        ":modal_price, :min_price, :max_price, :n_reports, :sources)"
    )
    with engine.begin() as conn:
        if start is None:
            conn.execute(text("TRUNCATE prices_clean"))
        else:
            conn.execute(text("DELETE FROM prices_clean WHERE date >= :s"), {"s": start})
        if not clean.empty:
            conn.execute(stmt, _records_any(clean, cols))
    return len(clean)


def _records_any(df: pd.DataFrame, columns: Sequence[str]) -> list[dict[str, Any]]:
    """Like _records but converts numpy scalars (int64 etc.) to plain Python values."""
    out = df.loc[:, list(columns)].astype(object)
    out = out.where(pd.notna(out), None)
    recs: list[dict[str, Any]] = out.to_dict(orient="records")  # type: ignore[assignment]
    for r in recs:
        for k, v in r.items():
            if hasattr(v, "item"):
                r[k] = v.item()
            elif isinstance(v, pd.Timestamp):
                r[k] = v.date()
    return recs


def insert_model_metrics(
    rows: pd.DataFrame, run_id: int | None, split: str, engine: Engine | None = None
) -> int:
    """Append aggregate metrics (model_name, model_version, commodity, horizon, metric, ...)."""
    if rows.empty:
        return 0
    engine = engine or get_engine()
    frame = rows.assign(run_id=run_id, split=split)
    cols = (
        "run_id",
        "model_name",
        "model_version",
        "split",
        "commodity",
        "horizon",
        "metric",
        "value",
        "naive_value",
    )
    stmt = text(
        "INSERT INTO model_metrics (run_id, model_name, model_version, split, commodity, "
        "horizon, metric, value, naive_value) VALUES (:run_id, :model_name, :model_version, "
        ":split, :commodity, :horizon, :metric, :value, :naive_value)"
    )
    with engine.begin() as conn:
        conn.execute(stmt, _records_any(frame, cols))
    return len(frame)
