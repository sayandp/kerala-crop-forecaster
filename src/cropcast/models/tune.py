"""Optional Optuna search (`--tune`): h=7, folds 1-3 only, p50 MAPE, <= 30 trials.

Folds 4-5 are never seen by the search, so the reported backtest stays honest.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import optuna
import pandas as pd

from cropcast.models.backtest import metrics_table, run_backtest
from cropcast.models.lgbm import DEFAULT_PARAMS, SEED

log = logging.getLogger(__name__)

TUNE_HORIZON = 7
TUNE_FOLDS = [1, 2, 3]
MAX_TRIALS = 30


def tune(
    features_h7: pd.DataFrame, prices: pd.DataFrame, last_date: date, n_trials: int = MAX_TRIALS
) -> dict[str, Any]:
    def objective(trial: optuna.Trial) -> float:
        params = {
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 8, 63, log=True),
            "min_child_samples": trial.suggest_int("min_child_samples", 20, 200, log=True),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "subsample_freq": 1,
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        }
        res = run_backtest(
            {TUNE_HORIZON: features_h7},
            prices,
            last_date,
            lgbm_params=params,
            fold_numbers=TUNE_FOLDS,
            quantiles=(0.5,),
        )
        preds = res.predictions[res.predictions["model"] == "lgbm"]
        return float(metrics_table(preds, [])["mape"].iloc[0])

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=SEED))
    study.optimize(objective, n_trials=min(n_trials, MAX_TRIALS))
    best = {**DEFAULT_PARAMS, **study.best_params, "subsample_freq": 1}
    log.info("tuning done", extra={"best_mape": study.best_value, "params": best})
    return best
