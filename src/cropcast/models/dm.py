"""Diebold-Mariano test for equal predictive accuracy (Phase 2.5 decision rule).

Loss = absolute percentage error (consistent with MAPE). With many series forecast on the
same dates, the loss differential is first averaged across series per target date (this
keeps cross-sectional correlation out of the variance), then tested for zero mean with a
Newey-West (HAC) variance using h-1 lags and the Harvey-Leybourne-Newbold small-sample
correction; p-values are two-sided from Student-t with T-1 df.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats


@dataclass(frozen=True)
class DMResult:
    stat: float  # negative = model has lower loss than the reference
    p_value: float
    mean_diff: float  # mean (loss_model - loss_reference), percentage points
    n_dates: int


def dm_test(
    loss_model: pd.Series, loss_reference: pd.Series, dates: pd.Series, horizon: int
) -> DMResult:
    d = (loss_model - loss_reference).groupby(pd.to_datetime(dates)).mean().sort_index()
    t = len(d)
    if t < 10 or float(d.std()) == 0.0:
        return DMResult(float("nan"), float("nan"), float(d.mean()) if t else float("nan"), t)
    lags = max(horizon - 1, 0)
    fit = sm.OLS(d.to_numpy(), np.ones(t)).fit(
        cov_type="HAC", cov_kwds={"maxlags": lags, "use_correction": True}
    )
    stat = float(fit.params[0] / fit.bse[0])
    hln = np.sqrt((t + 1 - 2 * horizon + horizon * (horizon - 1) / t) / t)
    stat *= hln
    p = float(2 * stats.t.sf(abs(stat), df=t - 1))
    return DMResult(stat, p, float(d.mean()), t)


def ape(actual: pd.Series, pred: pd.Series) -> pd.Series:
    return (pred - actual).abs() / actual * 100
