"""Pydantic response models (prices are Rs./quintal unless a field says per_kg)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str = Field(description="ok | degraded")
    db_ok: bool
    last_successful_run: datetime | None
    last_run_status: str | None
    db_size_mb: float | None
    checked_at: datetime


class Crop(BaseModel):
    crop: str
    n_markets: int


class Market(BaseModel):
    crop: str
    market: str
    variety: str
    last_observed: date | None
    latest_forecast: date | None


class Forecast(BaseModel):
    crop: str
    market: str
    variety: str
    horizon: int
    as_of: date = Field(description="forecast date: last data day used")
    target_date: date
    p10: float
    p50: float
    p90: float
    unit: str = "Rs./quintal"
    last_value: float | None
    last_observed: date | None
    stale: bool = Field(description="latest observed price is more than 3 days older than as_of")
    model_name: str | None
    model_version: str


class HistoryPoint(BaseModel):
    date: date
    modal_price: float
    min_price: float | None
    max_price: float | None


class History(BaseModel):
    crop: str
    market: str
    variety: str
    unit: str = "Rs./quintal"
    points: list[HistoryPoint]


class ChampionMetric(BaseModel):
    crop: str
    horizon: int
    mape_28d: float | None
    naive_mape_28d: float | None
    coverage_80_28d: float | None
    n_28d: int | None
    computed_at: datetime | None


class ShadowProgress(BaseModel):
    crop: str
    n_evaluated: int
    n_moves: int
    days_covered: int
    required_days: int = 84
    required_moves: int = 30
    verdict: str


class Metrics(BaseModel):
    champion: list[ChampionMetric]
    shadow: list[ShadowProgress]


class Badge(BaseModel):
    """shields.io endpoint schema."""

    schemaVersion: int = 1
    label: str
    message: str
    color: str
