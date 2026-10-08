"""Read-only queries for the API (engine on DATABASE_URL_RO; no pandas, no MLflow).

Every function returns plain Python data and is cached for `api_cache_ttl_s` seconds.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from functools import lru_cache, wraps
from typing import Any, TypeVar, cast

from sqlalchemy import Engine, create_engine, text

from cropcast.config import settings

F = TypeVar("F", bound=Callable[..., Any])
_cache: dict[tuple[Any, ...], tuple[float, Any]] = {}
_lock = threading.Lock()


def ttl_cache(fn: F) -> F:
    @wraps(fn)
    def wrapper(*args: Any) -> Any:
        key = (fn.__name__, *args)
        now = time.monotonic()
        with _lock:
            hit = _cache.get(key)
            if hit is not None and now - hit[0] < settings.api_cache_ttl_s:
                return hit[1]
        value = fn(*args)
        with _lock:
            _cache[key] = (now, value)
        return value

    return cast(F, wrapper)


def clear_cache() -> None:
    with _lock:
        _cache.clear()


_SCHEME = re.compile(r"^(postgres|postgresql)(\+\w+)?://")
_PASSWORD = re.compile(r"(://[^:/@\s]+:)[^@\s]+@")


def sqlalchemy_url(raw: str) -> str:
    """Any libpq-style Postgres URL (the one Vercel/Neon hand out) -> SQLAlchemy + psycopg 3.

    Accepts postgres://, postgresql://, postgresql+psycopg2:// and postgresql+psycopg://;
    strips whitespace and surrounding quotes (a common paste artefact in dashboards)."""
    url = raw.strip().strip("'\"").strip()
    if not _SCHEME.match(url):
        raise ValueError("DATABASE_URL_RO must start with postgres:// or postgresql://")
    return _SCHEME.sub("postgresql+psycopg://", url, count=1)


def redact(text_: str) -> str:
    """Hide the password of any URL in an error message before it is logged."""
    return _PASSWORD.sub(r"\1***@", text_)


@lru_cache(maxsize=1)
def engine() -> Engine:
    if not settings.database_url_ro:
        raise RuntimeError("DATABASE_URL_RO is not set (the API only uses the read-only role)")
    url = sqlalchemy_url(settings.database_url_ro)
    # Created lazily on the first request (no DB connection at import/startup). Timeouts bound
    # /health when Neon is waking up or unreachable (connect + statement <= api_db_timeout_s).
    timeout = settings.api_db_timeout_s
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
        pool_timeout=timeout,
        connect_args={
            "connect_timeout": max(1, int(timeout)),
            "options": f"-c statement_timeout={int(timeout * 1000)}",
        },
    )


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with engine().connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def health() -> dict[str, Any]:
    with engine().connect() as conn:
        size = conn.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
        last_ok = conn.execute(
            text("SELECT max(finished_at) FROM pipeline_runs WHERE status = 'success'")
        ).scalar()
        last = conn.execute(
            text("SELECT status FROM pipeline_runs ORDER BY started_at DESC LIMIT 1")
        ).scalar()
    return {
        "db_size_mb": round(int(size) / 1048576, 1),
        "last_successful_run": last_ok,
        "last_run_status": last,
    }


@ttl_cache
def crops() -> list[dict[str, Any]]:
    return _rows(
        """SELECT commodity AS crop, count(DISTINCT market) AS n_markets FROM forecasts
           WHERE forecast_date = (SELECT max(forecast_date) FROM forecasts)
           GROUP BY commodity ORDER BY commodity"""
    )


@ttl_cache
def markets(crop: str) -> list[dict[str, Any]]:
    return _rows(
        """SELECT f.commodity AS crop, f.market, f.variety, max(f.forecast_date) AS latest_forecast,
                  (SELECT max(c.date) FROM prices_clean c WHERE c.commodity = f.commodity
                     AND c.market = f.market AND c.variety = f.variety) AS last_observed
           FROM forecasts f WHERE f.commodity = :crop
           GROUP BY f.commodity, f.market, f.variety ORDER BY f.market""",
        crop=crop,
    )


@ttl_cache
def forecast(crop: str, market: str, horizon: int) -> dict[str, Any] | None:
    rows = _rows(
        """SELECT f.commodity AS crop, f.market, f.variety, f.horizon, f.forecast_date AS as_of,
                  f.target_date, f.p10::float8 AS p10, f.p50::float8 AS p50, f.p90::float8 AS p90,
                  f.last_value::float8 AS last_value, f.model_name, f.model_version,
                  (SELECT max(c.date) FROM prices_clean c WHERE c.commodity = f.commodity
                     AND c.market = f.market AND c.variety = f.variety
                     AND c.date <= f.forecast_date) AS last_observed
           FROM forecasts f
           WHERE f.commodity = :crop AND f.market = :market AND f.horizon = :h
           ORDER BY f.forecast_date DESC LIMIT 1""",
        crop=crop,
        market=market,
        h=horizon,
    )
    return rows[0] if rows else None


@ttl_cache
def history(crop: str, market: str, days: int) -> tuple[str | None, list[dict[str, Any]]]:
    variety = _rows(
        "SELECT variety FROM forecasts WHERE commodity = :c AND market = :m LIMIT 1",
        c=crop,
        m=market,
    )
    if not variety:
        return None, []
    v = str(variety[0]["variety"])
    pts = _rows(
        """SELECT date, modal_price::float8 AS modal_price, min_price::float8 AS min_price,
                  max_price::float8 AS max_price
           FROM prices_clean
           WHERE commodity = :c AND market = :m AND variety = :v
             AND date > (SELECT max(date) FROM prices_clean WHERE commodity = :c
                           AND market = :m AND variety = :v) - :days
           ORDER BY date""",
        c=crop,
        m=market,
        v=v,
        days=days,
    )
    return v, pts


@ttl_cache
def champion_metrics() -> list[dict[str, Any]]:
    return _rows(
        """WITH latest AS (
               SELECT max(computed_at) AS t FROM model_metrics
               WHERE split = 'live' AND model_name = 'champion')
           SELECT commodity AS crop, horizon,
                  max(value) FILTER (WHERE metric = 'mape_28d') AS mape_28d,
                  max(naive_value) FILTER (WHERE metric = 'mape_28d') AS naive_mape_28d,
                  max(value) FILTER (WHERE metric = 'coverage_80_28d') AS coverage_80_28d,
                  max(value) FILTER (WHERE metric = 'n_28d')::int AS n_28d,
                  max(computed_at) AS computed_at
           FROM model_metrics, latest
           WHERE split = 'live' AND model_name = 'champion'
             AND computed_at >= latest.t - interval '1 hour'
           GROUP BY commodity, horizon ORDER BY commodity, horizon"""
    )


@ttl_cache
def shadow_progress() -> list[dict[str, Any]]:
    return _rows(
        """WITH latest AS (
               SELECT max(computed_at) AS t FROM model_metrics
               WHERE split = 'live' AND model_name = 'move-h7-shadow'),
           m AS (
               SELECT commodity,
                      max(value) FILTER (WHERE metric = 'n')::int AS n,
                      max(value) FILTER (WHERE metric = 'n_moves')::int AS n_moves,
                      max(value) FILTER (WHERE metric = 'days_covered')::int AS days_covered
               FROM model_metrics, latest
               WHERE split = 'live' AND model_name = 'move-h7-shadow'
                 AND computed_at >= latest.t - interval '1 hour'
               GROUP BY commodity),
           v AS (
               SELECT DISTINCT ON (scope) scope, decision FROM promotion_log
               WHERE model_name = 'cropcast-move-h7' ORDER BY scope, decided_at DESC)
           SELECT c.crop, coalesce(m.n, 0) AS n_evaluated, coalesce(m.n_moves, 0) AS n_moves,
                  coalesce(m.days_covered, 0) AS days_covered,
                  coalesce(v.decision, 'insufficient data') AS verdict
           FROM (VALUES ('coconut'), ('pepper'), ('rubber'), ('tapioca')) AS c(crop)
           LEFT JOIN m ON m.commodity = c.crop LEFT JOIN v ON v.scope = c.crop
           ORDER BY c.crop"""
    )


@ttl_cache
def latest_members() -> int | None:
    rows = _rows("SELECT member_count FROM channel_stats ORDER BY date DESC LIMIT 1")
    return int(rows[0]["member_count"]) if rows else None


@ttl_cache
def bot_usage() -> dict[str, Any]:
    """Aggregates only (view bot_usage): the read-only role never sees chat ids."""
    rows = _rows("SELECT * FROM bot_usage")
    return rows[0] if rows else {}
