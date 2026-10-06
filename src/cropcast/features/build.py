"""Feature engineering — the single source of truth for training AND prediction.

    build_features(prices_clean, weather, asof, horizon) -> one row per (series, day d)

Row semantics: day `d` is the first day whose price is unknown; the forecast ORIGIN is
d - 1 (the last day of data that can be used) and the TARGET is the price on
origin + horizon. Every history-based feature is computed from the price series shifted
by one day (`.shift(1)` first), so it only sees data <= origin. On top of that, the inputs
are truncated to `asof` before anything is computed: nothing after `asof` can leak in.

* Training: rows with a known target (target_date <= asof).
* Prediction: the row with origin_date == asof (target NaN).

Target = log1p(modal_price) on target_date; never filled. Lag features are forward-filled
at most 3 days; `last_value` (the naive forecast) is the last observation at any age.
"""

from __future__ import annotations

import math
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from cropcast.config import settings
from cropcast.features.series import SERIES_KEY, Series
from cropcast.ingest.mappings import market_districts

LAGS = (1, 2, 3, 7, 14, 28)
ROLL_WINDOWS = (7, 28)
FFILL_LIMIT = 3  # max days a lag feature may be carried forward
MAX_STALENESS_DAYS = 7  # rows whose last observation is older are dropped (series not alive)
MIN_HISTORY_DAYS = 28  # burn-in so 28-day features exist
FESTIVALS_PATH = Path(__file__).resolve().parent / "festivals.yaml"

CATEGORICAL_FEATURES = ["commodity", "market", "variety"]
NUMERIC_FEATURES = [
    "log_last",
    *[f"lag_{k}_rel" for k in LAGS],
    *[f"roll_mean_{w}_rel" for w in ROLL_WINDOWS],
    *[f"roll_cv_{w}" for w in ROLL_WINDOWS],
    "pct_change_1",
    "pct_change_7",
    "spread",
    "n_reports",
    "days_since_last_obs",
    "obs_share_28",
    "dow",
    "month",
    "weekofyear",
    "fest_onam",
    "fest_vishu",
    "fest_christmas",
    "fest_ramzan",
    "fest_bakrid",
    "monsoon",
    "rain_7d",
    "rain_30d",
    "temp_mean_7d",
    "portal_v2",
    "horizon",
]
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
# Not model inputs: identifiers, baseline inputs (price level, Rs./quintal) and the target.
ID_COLUMNS = [*SERIES_KEY, "district", "origin_date", "target_date"]
BASELINE_COLUMNS = ["last_value", "seasonal_ref", "ma_7"]
TARGET = "target"
OUTPUT_COLUMNS = list(
    dict.fromkeys(ID_COLUMNS + FEATURE_COLUMNS + BASELINE_COLUMNS + [TARGET])
)  # ordered, de-duplicated (series keys are both IDs and categorical features)


@lru_cache(maxsize=1)
def festival_dates() -> dict[str, list[pd.Timestamp]]:
    data = yaml.safe_load(FESTIVALS_PATH.read_text(encoding="utf-8"))
    return {k: [pd.Timestamp(d) for d in v] for k, v in data["festivals"].items()}


def festival_window_days() -> int:
    data = yaml.safe_load(FESTIVALS_PATH.read_text(encoding="utf-8"))
    return int(data["window_days"])


def _festival_flags(target_dates: pd.Series) -> pd.DataFrame:
    win = pd.Timedelta(days=festival_window_days())
    out = {}
    for name, days in festival_dates().items():
        flag = np.zeros(len(target_dates), dtype=np.int8)
        td = target_dates.to_numpy(dtype="datetime64[ns]")
        for f in days:
            ft = np.datetime64(f.to_datetime64())
            flag |= ((td >= ft - win.to_timedelta64()) & (td <= ft)).astype(np.int8)
        out[f"fest_{name}"] = flag
    return pd.DataFrame(out, index=target_dates.index)


def _weather_features(weather: pd.DataFrame) -> pd.DataFrame:
    """Per (district, date): rain sum 7/30 d and mean temperature 7 d, windows ending on date."""
    if weather.empty:
        return pd.DataFrame(columns=["district", "date", "rain_7d", "rain_30d", "temp_mean_7d"])
    frames = []
    for district, g in weather.groupby("district"):
        s = g.assign(date=pd.to_datetime(g["date"])).set_index("date").sort_index()
        idx = pd.date_range(s.index.min(), s.index.max(), freq="D")
        s = s.reindex(idx)
        rain = pd.to_numeric(s["rainfall_mm"], errors="coerce")
        temp = pd.to_numeric(s["temp_mean_c"], errors="coerce")
        frames.append(
            pd.DataFrame(
                {
                    "district": district,
                    "date": idx,
                    "rain_7d": rain.rolling(7, min_periods=5).sum().to_numpy(),
                    "rain_30d": rain.rolling(30, min_periods=20).sum().to_numpy(),
                    "temp_mean_7d": temp.rolling(7, min_periods=5).mean().to_numpy(),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _series_frame(g: pd.DataFrame, asof: pd.Timestamp, horizon: int) -> pd.DataFrame:
    """All feature rows for one series. `g` holds that series' rows with date <= asof."""
    g = g.assign(date=pd.to_datetime(g["date"])).set_index("date").sort_index()
    first = g.index.min()
    # Day index runs to asof + 1 so that the prediction row (origin = asof) exists.
    idx = pd.date_range(first, asof + pd.Timedelta(days=1), freq="D")
    p = pd.to_numeric(g["modal_price"], errors="coerce").astype(float).reindex(idx)
    lo = pd.to_numeric(g["min_price"], errors="coerce").astype(float).reindex(idx)
    hi = pd.to_numeric(g["max_price"], errors="coerce").astype(float).reindex(idx)
    nrep = pd.to_numeric(g["n_reports"], errors="coerce").astype(float).reindex(idx)

    hist = p.shift(1)  # value known at the START of day d = price on origin d - 1
    x = p.ffill(limit=FFILL_LIMIT)  # lag source: at most 3-day carry-forward
    last_value = hist.ffill()  # naive forecast: last observation, any age
    obs_day = pd.Series(idx, index=idx).where(p.notna())
    last_obs_day = obs_day.shift(1).ffill()
    origin = pd.Series(idx - pd.Timedelta(days=1), index=idx)

    f = pd.DataFrame(index=idx)
    f["origin_date"] = origin
    f["target_date"] = origin + pd.Timedelta(days=horizon)
    f["last_value"] = last_value
    f["log_last"] = np.log1p(last_value)
    for k in LAGS:
        f[f"lag_{k}_rel"] = np.log1p(x.shift(k)) - f["log_last"]
    for w in ROLL_WINDOWS:
        roll = hist.rolling(w, min_periods=max(2, w // 4))
        mean, std = roll.mean(), roll.std()
        f[f"roll_mean_{w}_rel"] = np.log1p(mean) - f["log_last"]
        f[f"roll_cv_{w}"] = std / mean
    f["ma_7"] = hist.rolling(7, min_periods=1).mean()
    lag1, lag2, lag7 = x.shift(1), x.shift(2), x.shift(7)
    f["pct_change_1"] = lag1 / lag2 - 1
    f["pct_change_7"] = lag1 / lag7 - 1
    f["spread"] = ((hi - lo) / p).shift(1).ffill(limit=FFILL_LIMIT)
    f["n_reports"] = nrep.shift(1).ffill(limit=FFILL_LIMIT)
    f["days_since_last_obs"] = (origin - last_obs_day).dt.days
    f["obs_share_28"] = hist.notna().astype(float).rolling(28, min_periods=1).mean()
    # Seasonal naive (period 7): most recent same-weekday value at or before the origin.
    back = 7 * math.ceil(horizon / 7) - horizon
    f["seasonal_ref"] = x.shift(1 + back).fillna(last_value)

    # Target: log1p(price on target_date), only if target_date <= asof. Never filled.
    target_price = p.reindex(f["target_date"]).to_numpy()
    f[TARGET] = np.where(f["target_date"] <= asof, np.log1p(target_price), np.nan)

    keep = (
        (f["origin_date"] >= first + pd.Timedelta(days=MIN_HISTORY_DAYS))
        & f["last_value"].notna()
        & (f["days_since_last_obs"] <= MAX_STALENESS_DAYS)
    )
    out: pd.DataFrame = f.loc[keep].reset_index(drop=True)
    return out


def build_features(
    prices_clean: pd.DataFrame,
    weather: pd.DataFrame,
    asof: date,
    horizon: int,
    series: list[Series] | None = None,
) -> pd.DataFrame:
    """Feature rows for every series, using only data dated <= asof.

    Returns ID_COLUMNS + FEATURE_COLUMNS + BASELINE_COLUMNS + [TARGET]; rows without a
    target (target_date > asof, or a missing market day) are kept — callers drop them for
    training and keep origin_date == asof for prediction.
    """
    cutoff = pd.Timestamp(asof)
    prices = prices_clean.assign(date=pd.to_datetime(prices_clean["date"]))
    prices = prices[prices["date"] <= cutoff]
    wx = weather.assign(date=pd.to_datetime(weather["date"])) if len(weather) else weather
    if len(wx):
        wx = wx[wx["date"] <= cutoff]
    if series is not None:
        wanted = pd.DataFrame([s.__dict__ for s in series], columns=SERIES_KEY)
        prices = prices.merge(wanted, on=SERIES_KEY)

    parts = []
    for key, g in prices.groupby(SERIES_KEY, sort=True):
        fr = _series_frame(g, cutoff, horizon)
        commodity, market, variety = (str(v) for v in key)
        fr["commodity"], fr["market"], fr["variety"] = commodity, market, variety
        parts.append(fr)
    if not parts:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    out = pd.concat(parts, ignore_index=True)

    td = pd.to_datetime(out["target_date"])
    out["dow"] = td.dt.dayofweek
    out["month"] = td.dt.month
    out["weekofyear"] = td.dt.isocalendar().week.astype(int).to_numpy()
    out = pd.concat([out, _festival_flags(td)], axis=1)
    out["monsoon"] = td.dt.month.between(6, 9).astype(np.int8)
    out["portal_v2"] = (
        pd.to_datetime(out["origin_date"]) >= pd.Timestamp(settings.portal_switch_date)
    ).astype(np.int8)
    out["horizon"] = horizon

    out["district"] = out["market"].map(market_districts())
    wf = _weather_features(wx)
    out = out.merge(
        wf.rename(columns={"date": "origin_date"}), on=["district", "origin_date"], how="left"
    )

    cats = (
        {k: [getattr(s, k) for s in series] for k in SERIES_KEY}
        if series is not None
        else {k: sorted(prices[k].unique()) for k in SERIES_KEY}
    )
    for k in CATEGORICAL_FEATURES:
        out[k] = pd.Categorical(out[k], categories=sorted(set(cats[k])))
    return (
        out.loc[:, OUTPUT_COLUMNS].sort_values([*SERIES_KEY, "origin_date"]).reset_index(drop=True)
    )
