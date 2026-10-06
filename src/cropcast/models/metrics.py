"""Forecast accuracy metrics (computed in price space, Rs./quintal).

MASE scale = mean absolute one-step change between consecutive observations of the
series in its training window (Hyndman & Koehler), so MASE < 1 beats a naive forecast's
typical in-sample error.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cropcast.features.series import SERIES_KEY


def mase_scales(prices: pd.DataFrame, cutoff: pd.Timestamp) -> pd.Series:
    """Per-series MASE denominator from observations dated <= cutoff."""
    p = prices[pd.to_datetime(prices["date"]) <= cutoff].sort_values("date")
    diffs = p.groupby(SERIES_KEY, observed=True)["modal_price"].diff().abs()
    return diffs.groupby([p[k] for k in SERIES_KEY], observed=True).mean().rename("mase_scale")


def summarize(df: pd.DataFrame) -> pd.Series:
    """Metrics for one group of forecast rows (actual, pred, p10, p90, mase_scale)."""
    y, yhat = df["actual"].to_numpy(float), df["pred"].to_numpy(float)
    err = np.abs(y - yhat)
    out = {
        "n": len(df),
        "mape": float(np.mean(err / y) * 100),
        "smape": float(np.mean(2 * err / (np.abs(y) + np.abs(yhat))) * 100),
        "mase": float(np.mean(err / df["mase_scale"].to_numpy(float))),
    }
    if df["p10"].notna().all() and len(df):
        inside = (df["p10"] <= df["actual"]) & (df["actual"] <= df["p90"])
        out["coverage_80"] = float(inside.mean() * 100)
    else:
        out["coverage_80"] = float("nan")
    return pd.Series(out)
