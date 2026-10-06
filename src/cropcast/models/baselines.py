"""Baselines with the same fit/predict interface as the LightGBM forecaster.

All forecasters predict log1p(price) and return columns p10/p50/p90 (baselines: p50 only).
Inputs come from features/build.py (BASELINE_COLUMNS are price levels, Rs./quintal).
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd

QUANTILE_COLUMNS = ["p10", "p50", "p90"]


class Forecaster(Protocol):
    name: str

    def fit(self, train: pd.DataFrame) -> Forecaster: ...

    def predict(self, df: pd.DataFrame) -> pd.DataFrame: ...


class _ColumnBaseline:
    """Point forecast = log1p(one baseline column); no fitting needed."""

    name = "baseline"
    column = ""

    def fit(self, train: pd.DataFrame) -> _ColumnBaseline:
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        # Fall back to the last observation when the column is undefined (e.g. no price
        # in the 7-day MA window) so every baseline scores on exactly the same rows.
        level = df[self.column].astype(float).fillna(df["last_value"].astype(float))
        p50 = np.log1p(level.to_numpy())
        nan = np.full(len(df), np.nan)
        return pd.DataFrame({"p10": nan, "p50": p50, "p90": nan}, index=df.index)


class Naive(_ColumnBaseline):
    """Last observed price (any age)."""

    name = "naive"
    column = "last_value"


class SeasonalNaive(_ColumnBaseline):
    """Most recent same-weekday price at or before the origin (period 7)."""

    name = "seasonal_naive"
    column = "seasonal_ref"


class MovingAverage(_ColumnBaseline):
    """Mean of the observed prices over the 7 days ending at the origin."""

    name = "moving_average"
    column = "ma_7"


BASELINES: tuple[type[_ColumnBaseline], ...] = (Naive, SeasonalNaive, MovingAverage)
