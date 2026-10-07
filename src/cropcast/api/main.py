"""cropcast API — read-only, batch-served forecasts (never loads models).

Run: uv run uvicorn cropcast.api.main:app --reload
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response
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
from cropcast.config import settings

log = logging.getLogger(__name__)

STALE_DAYS = 3

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
def health(response: Response) -> Health:
    now = datetime.now(UTC)
    try:
        h = q.health()
    except Exception as exc:  # DB unreachable: report, don't crash
        log.warning("health: db error", extra={"error": type(exc).__name__})
        response.status_code = 503
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


@app.get("/badge/subscribers.json", response_model=Badge)
def badge_subscribers(request: Request) -> Badge:
    n = q.latest_members()
    return Badge(label="Telegram subscribers", message="—" if n is None else str(n), color="blue")
