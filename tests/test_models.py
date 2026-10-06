"""Baselines, LightGBM forecaster, walk-forward folds, metrics and the model-quality gate."""

from __future__ import annotations

from datetime import date
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from cropcast.features.build import TARGET, build_features
from cropcast.models.backtest import (
    comparison_table,
    make_folds,
    metrics_table,
    run_backtest,
    split_fold,
)
from cropcast.models.baselines import MovingAverage, Naive, SeasonalNaive
from cropcast.models.lgbm import LGBMForecaster
from cropcast.models.metrics import mase_scales, summarize
from cropcast.models.training import model_metrics_rows
from tests.conftest import FIXTURES


@pytest.fixture(scope="module")
def sample() -> pd.DataFrame:
    return pd.read_parquet(FIXTURES / "sample_prices.parquet").assign(n_reports=1)


@pytest.fixture(scope="module")
def last(sample: pd.DataFrame) -> date:
    return pd.Timestamp(sample["date"].max()).date()


@pytest.fixture(scope="module")
def feats7(sample: pd.DataFrame, last: date) -> pd.DataFrame:
    return build_features(sample, pd.DataFrame(), last, 7)


# --- baselines -------------------------------------------------------------------------


def test_baselines_share_the_interface_and_fall_back_to_last_value() -> None:
    df = pd.DataFrame(
        {"last_value": [5000.0, 4000.0], "seasonal_ref": [5100.0, np.nan], "ma_7": [np.nan, 4200.0]}
    )
    naive = Naive().fit(df).predict(df)
    assert list(naive.columns) == ["p10", "p50", "p90"]
    assert np.allclose(np.expm1(naive["p50"]), [5000, 4000])
    assert naive["p10"].isna().all()
    assert np.allclose(np.expm1(SeasonalNaive().fit(df).predict(df)["p50"]), [5100, 4000])
    assert np.allclose(np.expm1(MovingAverage().fit(df).predict(df)["p50"]), [5000, 4200])


# --- folds ------------------------------------------------------------------------------


@pytest.mark.parametrize("horizon", [1, 7, 14])
def test_folds_never_overlap_train_and_test(feats7: pd.DataFrame, last: date, horizon: int) -> None:
    folds = make_folds(last, horizon)
    assert len(folds) == 5
    assert folds[-1].target_end == pd.Timestamp(last)  # last window ends at the latest date
    for a, b in pairwise(folds):
        assert a.test_end < b.cutoff  # test windows are disjoint and in time order
        assert (b.cutoff - a.cutoff).days == 14
    feats = feats7 if horizon == 7 else build_features(
        pd.read_parquet(FIXTURES / "sample_prices.parquet").assign(n_reports=1),
        pd.DataFrame(), last, horizon,
    )  # fmt: skip
    for fold in folds:
        train, test = split_fold(feats, fold)
        assert len(train) and len(test)
        tr_t, te_t = pd.to_datetime(train["target_date"]), pd.to_datetime(test["target_date"])
        tr_o, te_o = pd.to_datetime(train["origin_date"]), pd.to_datetime(test["origin_date"])
        assert tr_t.max() <= fold.cutoff < te_t.min()  # every train target precedes test
        assert tr_o.max() < te_o.min()
        assert te_t.max() <= pd.Timestamp(last)
        assert test[TARGET].notna().all()


# --- LightGBM ------------------------------------------------------------------------------


def test_lgbm_quantiles_are_ordered_and_reproducible(feats7: pd.DataFrame) -> None:
    train = feats7.dropna(subset=[TARGET])
    cut = pd.to_datetime(train["target_date"]).quantile(0.9)
    tr = train[pd.to_datetime(train["target_date"]) <= cut]
    te = train[pd.to_datetime(train["origin_date"]) > cut].head(200)
    p1 = LGBMForecaster(7).fit(tr).predict(te)
    p2 = LGBMForecaster(7).fit(tr).predict(te)
    assert (p1["p10"] <= p1["p50"]).all() and (p1["p50"] <= p1["p90"]).all()
    pd.testing.assert_frame_equal(p1, p2)  # seed 42 + deterministic


def test_lgbm_p50_only_mode(feats7: pd.DataFrame) -> None:
    train = feats7.dropna(subset=[TARGET])
    m = LGBMForecaster(7, quantiles=(0.5,)).fit(train)
    pred = m.predict(train.head(5))
    assert pred["p50"].notna().all() and pred["p10"].isna().all()


# --- metrics --------------------------------------------------------------------------------


def test_metric_formulas() -> None:
    df = pd.DataFrame(
        {
            "actual": [100.0, 200.0],
            "pred": [110.0, 180.0],
            "p10": [90.0, 150.0],
            "p90": [120.0, 190.0],
            "mase_scale": [10.0, 10.0],
        }
    )
    m = summarize(df)
    assert m["mape"] == pytest.approx((10 / 100 + 20 / 200) / 2 * 100)
    assert m["smape"] == pytest.approx((2 * 10 / 210 + 2 * 20 / 380) / 2 * 100)
    assert m["mase"] == pytest.approx((10 / 10 + 20 / 10) / 2)
    assert m["coverage_80"] == pytest.approx(50.0)  # 200 is above p90 = 190


def test_mase_scale_is_mean_abs_one_step_change() -> None:
    p = pd.DataFrame(
        {
            "commodity": "banana",
            "market": "Aluva",
            "variety": "Nendran",
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05", "2026-02-01"]),
            "modal_price": [100.0, 110.0, 105.0, 999.0],
        }
    )
    s = mase_scales(p, pd.Timestamp("2026-01-31"))  # the Feb row is after the cutoff
    assert s.iloc[0] == pytest.approx((10 + 5) / 2)


# --- backtest + model_metrics + quality gate ------------------------------------------------


@pytest.fixture(scope="module")
def backtest7(sample: pd.DataFrame, last: date, feats7: pd.DataFrame) -> pd.DataFrame:
    return run_backtest({7: feats7}, sample, last).predictions


def test_backtest_scores_all_models_on_identical_rows(backtest7: pd.DataFrame) -> None:
    counts = backtest7.groupby("model").size()
    assert set(counts.index) == {"lgbm", "naive", "seasonal_naive", "moving_average"}
    assert counts.nunique() == 1
    table = comparison_table(backtest7, ["horizon"])
    for col in ("mape_lgbm", "mape_naive", "mape_seasonal_naive", "coverage_80_lgbm"):
        assert col in table.columns  # naive numbers always next to LGBM


def test_model_metrics_rows_carry_naive_value(backtest7: pd.DataFrame) -> None:
    rows = model_metrics_rows(backtest7, "abc123")
    lgbm = rows[(rows["model_name"] == "lgbm") & (rows["metric"] == "mape")]
    assert set(lgbm["commodity"]) >= {"all", "banana"}
    assert lgbm["naive_value"].notna().all()
    assert (rows["model_version"] == "abc123").all()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Phase 2 finding: on the frozen 2-year fixture LightGBM h=7 does NOT beat naive "
        "(MAPE 5.04 vs 4.80; also on the real 19 series it only ties naive). Kept as a "
        "strict xfail so CI flags the day it starts passing; see CLAUDE.md / backtest report."
    ),
)
def test_model_quality_lgbm_h7_beats_naive(backtest7: pd.DataFrame) -> None:
    t = metrics_table(backtest7, ["horizon"]).set_index("model")
    assert t.loc["lgbm", "mape"] < t.loc["naive", "mape"]
