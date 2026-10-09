"""Per-crop split-conformal calibration of the p10-p90 band (display only; no gate).

Conformalized quantile regression (Romano et al. 2019) in log1p space, per crop (product key) x
horizon. Conformity score of a matured forecast with band [lo, hi] and outcome y:

    s = max(log1p(lo) - log1p(y), log1p(y) - log1p(hi))   (> 0 outside the band)

The offset q is the ceil((n + 1) * 0.8) / n empirical quantile of the n most recent scores; the
calibrated band is [expm1(log1p(lo) - q), expm1(log1p(hi) + q)] (q < 0 narrows it). Scores come
only from forecasts whose target date had passed (no leakage). In production the weekly retrain
computes q from its 5-fold backtest (the last ~70 days of out-of-sample forecasts).
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
import pandas as pd

TARGET_COVERAGE = 0.80
MIN_SCORES = 20  # fewer matured forecasts than this -> no adjustment (offset 0)
WINDOW_DAYS = 70  # = the retrain's 5-fold x 14-day backtest


def scores(lo: pd.Series, hi: pd.Series, actual: pd.Series) -> pd.Series:
    y = np.log1p(actual.astype(float))
    s = np.maximum(np.log1p(lo.astype(float)) - y, y - np.log1p(hi.astype(float)))
    return pd.Series(s, index=actual.index, dtype=float)


def offset(s: pd.Series, coverage: float = TARGET_COVERAGE) -> float:
    """Finite-sample conformal quantile of the scores (0 if too few)."""
    s = s.dropna()
    n = len(s)
    if n < MIN_SCORES:
        return 0.0
    k = min(n, math.ceil((n + 1) * coverage))  # k-th smallest score (split-conformal)
    return float(np.sort(s.to_numpy())[k - 1])


def apply(
    lo: pd.Series, hi: pd.Series, q: pd.Series | float, mid: pd.Series | None = None
) -> tuple[pd.Series, pd.Series]:
    """Shift the band by q in log space; keep the point forecast inside it."""
    new_lo = pd.Series(np.expm1(np.log1p(lo.astype(float)) - q), index=lo.index, dtype=float)
    new_hi = pd.Series(np.expm1(np.log1p(hi.astype(float)) + q), index=hi.index, dtype=float)
    if mid is not None:
        new_lo = new_lo.clip(upper=mid.astype(float))
        new_hi = new_hi.clip(lower=mid.astype(float))
    return new_lo, new_hi


def offsets(matured: pd.DataFrame, key: str = "crop") -> dict[str, float]:
    """Offset per crop from matured forecasts with columns lo, hi, actual and `key`."""
    s = scores(matured["lo"], matured["hi"], matured["actual"])
    return {str(k): offset(s[g.index]) for k, g in matured.groupby(key)}


def served_band(preds: pd.DataFrame, crop_of: Callable[[str, str, str], str]) -> pd.DataFrame:
    """Backtest predictions -> one row per forecast with the SERVED band (LGBM quantile band
    around log1p(last price), clamped to contain the naive point) and the product key."""
    lg = preds[preds["model"] == "lgbm"].copy()
    nv = preds[preds["model"] == "naive"][
        ["commodity", "market", "variety", "origin_date", "horizon", "pred"]
    ]
    key = ["commodity", "market", "variety", "origin_date", "horizon"]
    out = lg.merge(nv.rename(columns={"pred": "naive"}), on=key, how="inner")
    out["lo"] = np.minimum(out["p10"].astype(float), out["naive"].astype(float))
    out["hi"] = np.maximum(out["p90"].astype(float), out["naive"].astype(float))
    out["crop"] = [
        crop_of(str(c), str(m), str(v))
        for c, m, v in zip(out["commodity"], out["market"], out["variety"], strict=True)
    ]
    out["origin_date"] = pd.to_datetime(out["origin_date"])
    out["target_date"] = pd.to_datetime(out["target_date"])
    return out


def rolling_calibrate(band: pd.DataFrame, window_days: int = WINDOW_DAYS) -> pd.DataFrame:
    """Calibrate each fold with offsets from the preceding `window_days` of forecasts whose
    targets had matured before the fold's first origin (what a weekly retrain can know)."""
    out = []
    for (h, _fold), g in band.groupby(["horizon", "fold"]):
        start = g["origin_date"].min()
        past = band[
            (band["horizon"] == h)
            & (band["target_date"] < start)
            & (band["origin_date"] >= start - pd.Timedelta(days=window_days))
        ]
        if past.empty:
            continue
        q = offsets(past)
        g = g.assign(
            q=g["crop"].map(q).fillna(0.0),
            n_cal=g["crop"].map(past["crop"].value_counts()).fillna(0),
        )
        g["lo_cal"], g["hi_cal"] = apply(g["lo"], g["hi"], g["q"], g["naive"])
        out.append(g)
    return pd.concat(out, ignore_index=True) if out else band.iloc[0:0]


def coverage(df: pd.DataFrame, lo: str, hi: str) -> float:
    inside = (df[lo] <= df["actual"]) & (df["actual"] <= df[hi])
    return float(inside.mean() * 100)
