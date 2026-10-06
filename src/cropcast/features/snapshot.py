"""One read of prices_clean (+ weather) per training invocation -> local parquet snapshot.

Training/backtesting never query Postgres per fold: they read these files.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, text

from cropcast.config import settings
from cropcast.features.series import SERIES_KEY, Series, series_frame

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Snapshot:
    prices: pd.DataFrame
    weather: pd.DataFrame
    prices_path: Path
    weather_path: Path

    @property
    def last_date(self) -> date:
        return pd.Timestamp(self.prices["date"].max()).date()

    @property
    def first_date(self) -> date:
        return pd.Timestamp(self.prices["date"].min()).date()


def snapshot_dir() -> Path:
    return settings.data_dir / "snapshots"


def take_snapshot(engine: Engine, series: list[Series], asof: date) -> Snapshot:
    """Read the modelled series from prices_clean and all district weather up to `asof`."""
    with engine.connect() as conn:
        prices = pd.read_sql(
            text(
                "SELECT commodity, market, variety, date, modal_price::float8 AS modal_price, "
                "min_price::float8 AS min_price, max_price::float8 AS max_price, n_reports, "
                "sources FROM prices_clean WHERE date <= :asof"
            ),
            conn,
            params={"asof": asof},
        )
        weather = pd.read_sql(
            text(
                "SELECT date, district, rainfall_mm::float8 AS rainfall_mm, "
                "temp_mean_c::float8 AS temp_mean_c FROM weather_daily WHERE date <= :asof"
            ),
            conn,
            params={"asof": asof},
        )
    prices = prices.merge(series_frame(series), on=SERIES_KEY)
    missing = set(map(tuple, series_frame(series).to_numpy())) - set(
        map(tuple, prices[SERIES_KEY].drop_duplicates().to_numpy())
    )
    if missing:
        raise ValueError(f"series in config/series.yaml not found in prices_clean: {missing}")
    out = snapshot_dir()
    out.mkdir(parents=True, exist_ok=True)
    pp, wp = out / f"prices_clean_{asof}.parquet", out / f"weather_{asof}.parquet"
    prices.to_parquet(pp, index=False)
    weather.to_parquet(wp, index=False)
    log.info(
        "snapshot written",
        extra={"prices_rows": len(prices), "weather_rows": len(weather), "path": str(pp)},
    )
    return Snapshot(prices, weather, pp, wp)


def load_snapshot(asof: date) -> Snapshot:
    pp = snapshot_dir() / f"prices_clean_{asof}.parquet"
    wp = snapshot_dir() / f"weather_{asof}.parquet"
    return Snapshot(pd.read_parquet(pp), pd.read_parquet(wp), pp, wp)
