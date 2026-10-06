"""MLflow pyfunc wrappers so every served model is registered and versioned the same way.

* PriceModel(point="naive"): p50 = last observed price (the champion); p10/p90 = LightGBM
  quantile models' change applied around the naive point in log1p space.
* PriceModel(point="lgbm"): p50 from the LightGBM p50 model (the price challenger).
* MoveModel: the E4a classifier -> p_down / p_flat / p_up / pred_class.

Input: rows from cropcast.features.build.build_features (FEATURE_COLUMNS + last_value).
Output prices are Rs./quintal.
"""

from __future__ import annotations

import json
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from mlflow.pyfunc.model import PythonModel

from cropcast.models.move import proba_frame


def _features(context: Any) -> list[str]:
    with open(context.artifacts["features"], encoding="utf-8") as fh:
        feats: list[str] = json.load(fh)
    return feats


class PriceModel(PythonModel):
    def __init__(self, point: str = "naive") -> None:
        if point not in ("naive", "lgbm"):
            raise ValueError(point)
        self.point = point

    def load_context(self, context: Any) -> None:
        self.features = _features(context)
        self.boosters = {
            q: lgb.Booster(model_file=context.artifacts[q])
            for q in ("p10", "p50", "p90")
            if q in context.artifacts
        }

    def predict(self, context: Any, model_input: pd.DataFrame, params: Any = None) -> pd.DataFrame:
        base = np.log1p(model_input["last_value"].astype(float).to_numpy())
        x = model_input[self.features]
        lo = base + self.boosters["p10"].predict(x)
        hi = base + self.boosters["p90"].predict(x)
        mid = base if self.point == "naive" else base + self.boosters["p50"].predict(x)
        lo, hi = np.minimum(lo, mid), np.maximum(hi, mid)  # interval always contains p50
        return pd.DataFrame(
            {"p10": np.expm1(lo), "p50": np.expm1(mid), "p90": np.expm1(hi)},
            index=model_input.index,
        )


class MoveModel(PythonModel):
    def load_context(self, context: Any) -> None:
        self.features = _features(context)
        self.booster = lgb.Booster(model_file=context.artifacts["classifier"])

    def predict(self, context: Any, model_input: pd.DataFrame, params: Any = None) -> pd.DataFrame:
        return proba_frame(self.booster, model_input, self.features)
