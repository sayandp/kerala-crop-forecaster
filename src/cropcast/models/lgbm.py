"""Global LightGBM quantile forecaster (one instance per horizon = direct multi-horizon).

* One model per quantile (alpha 0.1 / 0.5 / 0.9); p50 is the point forecast.
* Learns the log-change y = target - log1p(last value) (trees cannot extrapolate price
  levels; pepper/rubber doubled over the history) and adds it back, so outputs are still
  log1p(modal_price).
* Early stopping on the last 28 days of the training window (by target date), then a
  refit on the whole window with the best iteration count.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from cropcast.features.build import FEATURE_COLUMNS, TARGET

log = logging.getLogger(__name__)

SEED = 42
QUANTILES = (0.1, 0.5, 0.9)
DEFAULT_PARAMS: dict[str, Any] = {
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 50,
    "colsample_bytree": 0.8,
    "subsample": 0.8,
    "subsample_freq": 1,
    "reg_lambda": 1.0,
}
MAX_ROUNDS = 2000
EARLY_STOPPING_ROUNDS = 100
VALIDATION_DAYS = 28


def _qname(alpha: float) -> str:
    return f"p{round(alpha * 100):02d}"


@dataclass
class LGBMForecaster:
    horizon: int
    params: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    quantiles: tuple[float, ...] = QUANTILES
    features: list[str] = field(default_factory=lambda: list(FEATURE_COLUMNS))
    name: str = "lgbm"
    models: dict[str, lgb.LGBMRegressor] = field(default_factory=dict)
    best_iterations: dict[str, int] = field(default_factory=dict)

    def _model(self, alpha: float, n_estimators: int) -> lgb.LGBMRegressor:
        return lgb.LGBMRegressor(
            objective="quantile",
            alpha=alpha,
            n_estimators=n_estimators,
            random_state=SEED,
            deterministic=True,
            force_col_wise=True,
            n_jobs=4,
            verbose=-1,
            **self.params,
        )

    def fit(self, train: pd.DataFrame) -> LGBMForecaster:
        data = train.dropna(subset=[TARGET])
        y = (data[TARGET] - data["log_last"]).to_numpy()
        target_dates = pd.to_datetime(data["target_date"])
        split = target_dates.max() - pd.Timedelta(days=VALIDATION_DAYS)
        is_val = (target_dates > split).to_numpy()
        x = data[self.features]
        for alpha in self.quantiles:
            q = _qname(alpha)
            es = self._model(alpha, MAX_ROUNDS)
            es.fit(
                x[~is_val],
                y[~is_val],
                eval_X=(x[is_val],),
                eval_y=(y[is_val],),
                eval_metric="quantile",
                callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False)],
            )
            best = max(int(es.best_iteration_ or MAX_ROUNDS), 50)
            self.best_iterations[q] = best
            self.models[q] = self._model(alpha, best).fit(x, y)
        log.info(
            "lgbm fitted",
            extra={"horizon": self.horizon, "rows": len(data), "best_iter": self.best_iterations},
        )
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        base = df["log_last"].to_numpy()
        preds = {q: base + m.predict(df[self.features]) for q, m in self.models.items()}
        out = pd.DataFrame(preds, index=df.index).reindex(columns=["p10", "p50", "p90"])
        if out.notna().all().all():
            # Quantile models are fitted independently: enforce p10 <= p50 <= p90.
            out[:] = np.sort(out.to_numpy(), axis=1)
        return out

    def feature_importance(self, quantile: str = "p50") -> pd.Series:
        booster = self.models[quantile].booster_
        gain = booster.feature_importance(importance_type="gain")
        return pd.Series(gain, index=booster.feature_name()).sort_values(ascending=False)

    def save(self, directory: Path) -> list[Path]:
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for q, m in self.models.items():
            path = directory / f"lgbm_h{self.horizon}_{q}.txt"
            m.booster_.save_model(str(path))
            paths.append(path)
        return paths
