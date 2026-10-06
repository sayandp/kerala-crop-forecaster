"""E4a move classifier: up (> +3 %) / down (< -3 %) / flat at h = 7.

This is the pre-registered challenger (reports/preregistration_e4a.md). Its SPEC (features,
parameters, thresholds, training scope, this file's training code) is hashed; shadow
predictions record the hash and the live evaluation only counts the current spec.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from cropcast.features.build import FEATURE_COLUMNS, TARGET
from cropcast.features.series import Series
from cropcast.models.lgbm import DEFAULT_PARAMS, EARLY_STOPPING_ROUNDS, SEED, VALIDATION_DAYS

HORIZON = 7
THRESHOLD = 0.03
CLASSES = ("down", "flat", "up")  # encoded 0, 1, 2
JUDGED_CROPS = ("coconut", "pepper", "rubber", "tapioca")  # banana excluded (prereg)


def move_classes(change: pd.Series | np.ndarray, threshold: float = THRESHOLD) -> np.ndarray:
    """Relative change -> 0 down / 1 flat / 2 up."""
    c = np.asarray(change, dtype=float)
    return np.select([c > threshold, c < -threshold], [2, 0], default=1)


def realised_move(features: pd.DataFrame) -> pd.Series:
    """price(target) / last_value - 1 for rows with a known target."""
    out: pd.Series = np.expm1(features[TARGET]) / features["last_value"] - 1
    return out


def trend_class(features: pd.DataFrame) -> np.ndarray:
    """Trend-persistence baseline: class of the series' 7-day change at forecast time."""
    return move_classes(features["pct_change_7"].fillna(0.0))


def _params() -> dict[str, Any]:
    return {
        "objective": "multiclass",
        "class_weight": "balanced",
        "random_state": SEED,
        "deterministic": True,
        "force_col_wise": True,
        "verbose": -1,
        "n_jobs": 4,
        **DEFAULT_PARAMS,
    }


@dataclass
class MoveClassifier:
    features: list[str] = field(default_factory=lambda: list(FEATURE_COLUMNS))
    model: lgb.LGBMClassifier | None = None
    best_iteration: int = 0

    def fit(self, train: pd.DataFrame) -> MoveClassifier:
        data = train.dropna(subset=[TARGET])
        y = move_classes(realised_move(data))
        td = pd.to_datetime(data["target_date"])
        val = (td > td.max() - pd.Timedelta(days=VALIDATION_DAYS)).to_numpy()
        x = data[self.features]
        es = lgb.LGBMClassifier(n_estimators=2000, **_params()).fit(
            x[~val],
            y[~val],
            eval_X=(x[val],),
            eval_y=(y[val],),
            callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False)],
        )
        self.best_iteration = max(int(es.best_iteration_ or 50), 50)
        self.model = lgb.LGBMClassifier(n_estimators=self.best_iteration, **_params()).fit(x, y)
        return self

    def save(self, path: Path) -> Path:
        assert self.model is not None
        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.booster_.save_model(str(path))
        return path


def spec(series: list[Series]) -> dict[str, Any]:
    return {
        "horizon": HORIZON,
        "threshold": THRESHOLD,
        "features": list(FEATURE_COLUMNS),
        "params": {k: v for k, v in _params().items() if k != "n_jobs"},
        "early_stopping": {"validation_days": VALIDATION_DAYS, "rounds": EARLY_STOPPING_ROUNDS},
        "training_series": sorted(f"{s.commodity}|{s.market}|{s.variety}" for s in series),
        "code": hashlib.sha256(
            (inspect.getsource(MoveClassifier) + inspect.getsource(move_classes)).encode()
        ).hexdigest(),
    }


def spec_hash(series: list[Series]) -> str:
    blob = json.dumps(spec(series), sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def proba_frame(booster: lgb.Booster, df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    p = np.asarray(booster.predict(df[features]))
    out = pd.DataFrame(p, columns=["p_down", "p_flat", "p_up"], index=df.index)
    out["pred_class"] = [CLASSES[i] for i in p.argmax(axis=1)]
    return out
