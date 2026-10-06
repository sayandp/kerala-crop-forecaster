"""Walk-forward backtest: expanding window, N folds x 14-day test windows. Never shuffled.

Fold k has a cutoff c_k. Training rows: target_date <= c_k (known at c_k). Test rows:
origin_date in [c_k, c_k + test_days - 1], i.e. a model trained at c_k forecasting from 14
consecutive origins with fresh data, as in production. So train targets < test targets and
train origins < test origins. Windows are per horizon: the last fold's TARGET dates end at
the latest observed date.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from cropcast.features.build import TARGET
from cropcast.features.series import SERIES_KEY
from cropcast.models.baselines import BASELINES, Forecaster
from cropcast.models.lgbm import LGBMForecaster
from cropcast.models.metrics import mase_scales, summarize

log = logging.getLogger(__name__)

MODEL_ORDER = ["lgbm", "naive", "seasonal_naive", "moving_average"]


@dataclass(frozen=True)
class Fold:
    number: int  # 1 = oldest
    horizon: int
    cutoff: pd.Timestamp  # = first test origin
    test_end: pd.Timestamp  # last test origin

    @property
    def target_start(self) -> pd.Timestamp:
        return self.cutoff + pd.Timedelta(days=self.horizon)

    @property
    def target_end(self) -> pd.Timestamp:
        return self.test_end + pd.Timedelta(days=self.horizon)


def make_folds(last_date: date, horizon: int, n_folds: int = 5, test_days: int = 14) -> list[Fold]:
    last = pd.Timestamp(last_date)
    folds = []
    for k in range(n_folds):
        end = last - pd.Timedelta(days=horizon + test_days * (n_folds - 1 - k))
        folds.append(Fold(k + 1, horizon, end - pd.Timedelta(days=test_days - 1), end))
    return folds


def split_fold(features: pd.DataFrame, fold: Fold) -> tuple[pd.DataFrame, pd.DataFrame]:
    known = features.dropna(subset=[TARGET])
    origin = pd.to_datetime(known["origin_date"])
    train = known[pd.to_datetime(known["target_date"]) <= fold.cutoff]
    test = known[(origin >= fold.cutoff) & (origin <= fold.test_end)]
    return train, test


@dataclass
class BacktestResult:
    predictions: pd.DataFrame
    folds: list[Fold]
    importances: dict[int, pd.Series] = field(default_factory=dict)


def run_backtest(
    features_by_h: dict[int, pd.DataFrame],
    prices: pd.DataFrame,
    last_date: date,
    lgbm_params: dict[str, Any] | None = None,
    n_folds: int = 5,
    test_days: int = 14,
    fold_numbers: list[int] | None = None,
    quantiles: tuple[float, ...] | None = None,
    on_fold: Callable[[Fold, pd.DataFrame], None] | None = None,
) -> BacktestResult:
    rows: list[pd.DataFrame] = []
    all_folds: list[Fold] = []
    last_lgbm: dict[int, LGBMForecaster] = {}
    for h, feats in sorted(features_by_h.items()):
        folds = make_folds(last_date, h, n_folds, test_days)
        if fold_numbers:
            folds = [f for f in folds if f.number in fold_numbers]
        all_folds.extend(folds)
        for fold in folds:
            train, test = split_fold(feats, fold)
            if test.empty:
                continue
            lgbm = LGBMForecaster(h)
            if lgbm_params:
                lgbm.params = dict(lgbm_params)
            if quantiles:
                lgbm.quantiles = quantiles
            lgbm.fit(train)
            last_lgbm[h] = lgbm
            models: list[Forecaster] = [lgbm, *(b().fit(train) for b in BASELINES)]
            scales = mase_scales(prices, fold.cutoff)
            base = test[[*SERIES_KEY, "origin_date", "target_date", TARGET]].copy()
            for k in SERIES_KEY:
                base[k] = base[k].astype(str)
            base = base.merge(scales.reset_index(), on=SERIES_KEY, how="left")
            for m in models:
                pred = m.predict(test)
                part = base.assign(
                    model=m.name,
                    horizon=h,
                    fold=fold.number,
                    actual=np.expm1(base[TARGET].to_numpy(float)),
                    pred=np.expm1(pred["p50"].to_numpy(float)),
                    p10=np.expm1(pred["p10"].to_numpy(float)),
                    p90=np.expm1(pred["p90"].to_numpy(float)),
                )
                rows.append(part.drop(columns=[TARGET]))
            if on_fold is not None:
                on_fold(fold, pd.concat(rows[-len(models) :], ignore_index=True))
    predictions = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    importances = {
        h: m.feature_importance() for h, m in last_lgbm.items() if "p50" in m.models
    }  # from the latest fold's p50 model
    return BacktestResult(predictions, all_folds, importances)


def metrics_table(predictions: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Long table: one row per (by..., model) with n, mape, smape, mase, coverage_80."""
    out = (
        predictions.groupby([*by, "model"], observed=True)[
            ["actual", "pred", "p10", "p90", "mase_scale"]
        ]
        .apply(summarize)
        .reset_index()
    )
    out["model"] = pd.Categorical(out["model"], MODEL_ORDER)
    return out.sort_values([*by, "model"]).reset_index(drop=True)


def comparison_table(predictions: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Wide table: LGBM metrics with naive / seasonal-naive / MA next to every number."""
    long = metrics_table(predictions, by)
    wide = long.pivot_table(
        index=by,
        columns="model",
        values=["mape", "smape", "mase", "coverage_80", "n"],
        observed=True,
    )
    wide.columns = ["_".join(map(str, col)) for col in wide.columns.to_list()]
    keep = [
        "n_lgbm",
        "mape_lgbm", "mape_naive", "mape_seasonal_naive", "mape_moving_average",
        "smape_lgbm", "smape_naive", "smape_seasonal_naive",
        "mase_lgbm", "mase_naive", "mase_seasonal_naive",
        "coverage_80_lgbm",
    ]  # fmt: skip
    wide = wide[[c for c in keep if c in wide.columns]].reset_index()
    wide["lgbm_beats_naive"] = wide["mape_lgbm"] < wide["mape_naive"]
    return wide
