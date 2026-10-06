"""Extra features for the Phase 2.5 experiments (E1 arrivals, E2 upstream markets).

All are keyed by (series, origin_date) and use data dated <= origin only (lag features are
carried forward at most 3 days, like features/build.py). They are merged onto the frame
from build_features; if an experiment wins they move into features/build.py in Phase 3.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cropcast.features.series import SERIES_KEY

FFILL = 3

ARRIVAL_FEATURES = [
    "arr_lag_1",
    "arr_lag_7",
    "arr_ratio_28",
    "kerala_arr_lag_1",
    "kerala_arr_ratio_28",
]
UPSTREAM_FEATURES = [f"up{k}_chg_{n}" for k in (1, 2) for n in (1, 3, 7)]


def _daily(s: pd.Series, end: pd.Timestamp) -> pd.Series:
    s = s.sort_index()
    return s.reindex(pd.date_range(s.index.min(), end, freq="D"))


def arrival_features(
    prices: pd.DataFrame, kerala_totals: pd.DataFrame, end: pd.Timestamp
) -> pd.DataFrame:
    """Per series and origin day: own arrivals (lag 1 / 7, ratio to 28-day mean) and the
    commodity's Kerala-wide total arrivals (lag 1, ratio to 28-day mean)."""
    parts = []
    for key, g in prices.groupby(SERIES_KEY, sort=True):
        a = _daily(g.set_index(pd.to_datetime(g["date"]))["arrivals_tonnes"].astype(float), end)
        x = a.ffill(limit=FFILL)
        mean28 = a.rolling(28, min_periods=5).mean()  # observed days only
        parts.append(
            pd.DataFrame(
                {
                    "commodity": key[0],
                    "market": key[1],
                    "variety": key[2],
                    "origin_date": x.index,
                    "arr_lag_1": np.log1p(x.to_numpy()),
                    "arr_lag_7": np.log1p(x.shift(6).to_numpy()),
                    "arr_ratio_28": (x / mean28).to_numpy(),
                }
            )
        )
    own = pd.concat(parts, ignore_index=True)
    tots = []
    for crop, g in kerala_totals.groupby("commodity"):
        t = _daily(g.set_index(pd.to_datetime(g["date"]))["total_tonnes"].astype(float), end)
        x = t.ffill(limit=FFILL)
        tots.append(
            pd.DataFrame(
                {
                    "commodity": crop,
                    "origin_date": x.index,
                    "kerala_arr_lag_1": np.log1p(x.to_numpy()),
                    "kerala_arr_ratio_28": (x / t.rolling(28, min_periods=5).mean()).to_numpy(),
                }
            )
        )
    return own.merge(
        pd.concat(tots, ignore_index=True), on=["commodity", "origin_date"], how="left"
    )


def upstream_index(upstream: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    """Daily median log price of the top-N markets (by #days) per (crop, state, commodity).

    Each market's log price is carried forward <= 3 days so the median is not driven by
    which markets happened to report on a day.
    """
    out = []
    for (crop, state, cmdt), g in upstream.groupby(["crop", "state", "commodity"]):
        g = g.dropna(subset=["date", "modal_price"])
        g = g[g["modal_price"] > 0]
        top = g.groupby("market")["date"].nunique().sort_values(ascending=False).head(top_n).index
        g = g[g["market"].isin(top)]
        wide = (
            g.assign(lp=np.log(g["modal_price"].astype(float)), date=pd.to_datetime(g["date"]))
            .groupby(["date", "market"])["lp"]
            .median()
            .unstack()
            .asfreq("D")
            .ffill(limit=FFILL)
        )
        out.append(
            pd.DataFrame(
                {
                    "crop": crop,
                    "state": state,
                    "commodity": cmdt,
                    "date": wide.index,
                    "log_index": wide.median(axis=1, skipna=True).to_numpy(),
                    "n_markets": wide.notna().sum(axis=1).to_numpy(),
                }
            )
        )
    return pd.concat(out, ignore_index=True)


# Kerala crop -> (primary, secondary) upstream source (state, commodity name).
UPSTREAM_SOURCES: dict[str, list[tuple[str, str]]] = {
    "banana": [("Tamil Nadu", "Banana"), ("Karnataka", "Banana")],
    "coconut": [("Tamil Nadu", "Coconut"), ("Karnataka", "Coconut")],
    "pepper": [("Karnataka", "Black pepper")],
    "tapioca": [("Tamil Nadu", "Tapioca")],
}


def upstream_features(index: pd.DataFrame) -> pd.DataFrame:
    """Per Kerala crop and origin day: lagged 1/3/7-day log change of each upstream index."""
    rows = []
    for crop, sources in UPSTREAM_SOURCES.items():
        frame: pd.DataFrame | None = None
        for k, (state, cmdt) in enumerate(sources, start=1):
            s = index[(index["state"] == state) & (index["commodity"] == cmdt)]
            if s.empty:
                continue
            li = s.set_index("date")["log_index"].sort_index()
            f = pd.DataFrame(
                {f"up{k}_chg_{n}": (li - li.shift(n)).to_numpy() for n in (1, 3, 7)},
                index=li.index,
            )
            frame = f if frame is None else frame.join(f, how="outer")
        if frame is not None:
            rows.append(frame.reset_index(names="origin_date").assign(commodity=crop))
    out = pd.concat(rows, ignore_index=True)
    return out.reindex(columns=["commodity", "origin_date", *UPSTREAM_FEATURES])


def merge_extra(features: pd.DataFrame, extra: pd.DataFrame, on: list[str]) -> pd.DataFrame:
    left = features.copy()
    left["origin_date"] = pd.to_datetime(left["origin_date"])
    keys = {k: left[k].astype(str) for k in on if k != "origin_date"}
    right = extra.copy()
    right["origin_date"] = pd.to_datetime(right["origin_date"])
    for k in keys:
        right[k] = right[k].astype(str)
    tmp = left.assign(**{f"_{k}": v for k, v in keys.items()})
    right = right.rename(columns={k: f"_{k}" for k in keys})
    merged = tmp.merge(right, on=[f"_{k}" if k in keys else k for k in on], how="left").drop(
        columns=[f"_{k}" for k in keys]
    )
    return merged
