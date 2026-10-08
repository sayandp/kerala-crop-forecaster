"""cropcast API — read-only, batch-served forecasts (never loads models).

Run: uv run uvicorn cropcast.api.main:app --reload
"""

from __future__ import annotations

import hmac
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import BackgroundTasks, Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from cropcast.api import queries as q
from cropcast.api.schemas import (
    Badge,
    ChampionMetric,
    Crop,
    Forecast,
    Health,
    History,
    HistoryPoint,
    Market,
    Metrics,
    ShadowProgress,
)
from cropcast.bot.telegram import webhook_path_token
from cropcast.config import settings
from cropcast.logging_setup import setup_logging

setup_logging()  # structured JSON lines to stdout (Render logs); no file, no DB
log = logging.getLogger(__name__)

STALE_DAYS = 3
# One background thread for the health DB probe so a hung connect can't block the response.
_health_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="health")

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.api_rate_limit])
app = FastAPI(
    title="cropcast API",
    version="1.0",
    description=(
        "Read-only daily forecasts of Kerala mandi prices (Agmarknet). Prices are Rs./quintal. "
        "The champion is the naive forecast (last price) with a LightGBM p10-p90 band; see the "
        "repository for why."
    ),
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"], allow_headers=["*"]
)

Crop_ = Annotated[str, Query(min_length=2, max_length=40, pattern=r"^[a-z]+$")]
Market_ = Annotated[str, Query(min_length=2, max_length=60)]


@app.get("/health", response_model=Health)
def health() -> Health:
    """Always 200 within ~api_db_timeout_s (8 s), for Render's health check: the service is up
    even when Neon is slow or down; that is reported as db_ok=false / status=degraded."""
    now = datetime.now(UTC)
    try:
        h = _health_pool.submit(q.health).result(timeout=settings.api_db_timeout_s)
    except Exception as exc:  # DB slow (TimeoutError) / unreachable: report, don't crash
        log.warning(
            "health: db unavailable",
            extra={
                "error": type(exc).__name__,
                "detail": q.redact(str(exc))[:500] or "timed out",
                "timeout_s": settings.api_db_timeout_s,
            },
        )
        return Health(
            status="degraded",
            db_ok=False,
            last_successful_run=None,
            last_run_status=None,
            db_size_mb=None,
            checked_at=now,
        )
    return Health(status="ok", db_ok=True, checked_at=now, **h)


@app.get("/crops", response_model=list[Crop])
def crops() -> list[Crop]:
    return [Crop(**r) for r in q.crops()]


@app.get("/markets", response_model=list[Market])
def markets(crop: Crop_) -> list[Market]:
    rows = q.markets(crop)
    if not rows:
        raise HTTPException(404, f"unknown crop {crop!r}")
    return [Market(**r) for r in rows]


@app.get("/forecast", response_model=Forecast)
def forecast(
    crop: Crop_, market: Market_, horizon: Annotated[int, Query(ge=1, le=14)] = 7
) -> Forecast:
    if horizon not in (1, 7, 14):
        raise HTTPException(422, "horizon must be 1, 7 or 14")
    r = q.forecast(crop, market, horizon)
    if r is None:
        raise HTTPException(404, f"no forecast for {crop}/{market}")
    stale = r["last_observed"] is None or (r["as_of"] - r["last_observed"]).days > STALE_DAYS
    return Forecast(stale=stale, **r)


@app.get("/history", response_model=History)
def history(
    crop: Crop_, market: Market_, days: Annotated[int, Query(ge=7, le=365)] = 90
) -> History:
    variety, pts = q.history(crop, market, days)
    if variety is None:
        raise HTTPException(404, f"unknown series {crop}/{market}")
    return History(
        crop=crop, market=market, variety=variety, points=[HistoryPoint(**p) for p in pts]
    )


@app.get("/metrics", response_model=Metrics)
def metrics() -> Metrics:
    return Metrics(
        champion=[ChampionMetric(**r) for r in q.champion_metrics()],
        shadow=[ShadowProgress(**r) for r in q.shadow_progress()],
    )


@app.get("/badge/coverage.json", response_model=Badge)
def badge_coverage(request: Request) -> Badge:
    row = next((r for r in q.champion_metrics() if r["crop"] == "all" and r["horizon"] == 7), None)
    cov = row["coverage_80_28d"] if row else None
    if cov is None:
        return Badge(label="p10-p90 coverage", message="collecting", color="lightgrey")
    color = "brightgreen" if 72 <= cov <= 88 else "orange"
    return Badge(
        label="p10-p90 coverage (7d, 28d live)", message=f"{cov:.0f}% (target 80%)", color=color
    )


@app.get("/badge/bot-users.json", response_model=Badge)
def badge_bot_users(request: Request) -> Badge:
    n = q.bot_usage().get("active_30d")
    return Badge(label="bot users (30 d)", message="—" if n is None else str(n), color="blue")


# --- Telegram bot (Phase 5) ---------------------------------------------------------------------


_bot: Any = None


def _process_update(update: dict[str, Any]) -> None:
    """Runs after the 200 has been sent. Never raises (Telegram must not see errors)."""
    global _bot
    try:
        if _bot is None:
            from cropcast.bot.handlers import Bot
            from cropcast.bot.store import Store

            _bot = Bot(Store.for_api())
        _bot.handle(update)
    except Exception as exc:
        log.error(
            "telegram update failed",
            extra={"error": type(exc).__name__, "detail": q.redact(str(exc))[:300]},
        )


@app.post("/telegram/webhook/{secret_path}", include_in_schema=False)
@limiter.exempt  # type: ignore[untyped-decorator]  # Telegram's few IPs carry every user
def telegram_webhook(
    secret_path: str,
    background: BackgroundTasks,
    update: Annotated[dict[str, Any], Body()],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    token = webhook_path_token()
    if token is None or not hmac.compare_digest(secret_path, token):
        raise HTTPException(status_code=404)
    expected = settings.telegram_webhook_secret
    given = x_telegram_bot_api_secret_token or ""
    if expected is None or not hmac.compare_digest(given, expected.get_secret_value()):
        raise HTTPException(status_code=403, detail="bad secret token")
    background.add_task(_process_update, update)  # answer 200 first; Telegram retries slow replies
    return {"ok": True}


@app.get("/badge/subscribers.json", response_model=Badge)
def badge_subscribers(request: Request) -> Badge:
    n = q.latest_members()
    return Badge(label="Telegram subscribers", message="—" if n is None else str(n), color="blue")
