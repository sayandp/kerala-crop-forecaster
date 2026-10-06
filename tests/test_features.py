"""Feature engineering: no leakage, target alignment, staleness, calendar/festival flags."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from cropcast.features.build import (
    FEATURE_COLUMNS,
    TARGET,
    build_features,
)
from cropcast.features.series import Series
from tests.conftest import FIXTURES


@pytest.fixture(scope="module")
def prices() -> pd.DataFrame:
    df = pd.read_parquet(FIXTURES / "sample_prices.parquet")
    return df.assign(n_reports=1)


@pytest.fixture(scope="module")
def weather(prices: pd.DataFrame) -> pd.DataFrame:
    days = pd.date_range(prices["date"].min(), prices["date"].max(), freq="D")
    rng = np.random.default_rng(0)
    return pd.concat(
        [
            pd.DataFrame(
                {
                    "date": days,
                    "district": d,
                    "rainfall_mm": rng.gamma(1.0, 8.0, len(days)),
                    "temp_mean_c": 27 + rng.normal(0, 1, len(days)),
                }
            )
            for d in sorted(prices["district"].dropna().unique())
        ]
    )


def _mutate_after(df: pd.DataFrame, asof: pd.Timestamp, col: str) -> pd.DataFrame:
    out = df.copy()
    after = pd.to_datetime(out["date"]) > asof
    out.loc[after, col] = out.loc[after, col] * 7.3 + 11
    return out


@pytest.mark.parametrize("horizon", [1, 7, 14])
def test_mutating_data_after_asof_changes_nothing(
    prices: pd.DataFrame, weather: pd.DataFrame, horizon: int
) -> None:
    asof = pd.Timestamp("2025-12-31")
    base = build_features(prices, weather, asof.date(), horizon)
    p2 = _mutate_after(prices, asof, "modal_price")
    p2 = _mutate_after(p2, asof, "min_price")
    w2 = _mutate_after(weather, asof, "rainfall_mm")
    mutated = build_features(p2, w2, asof.date(), horizon)
    pd.testing.assert_frame_equal(base, mutated)


@pytest.mark.parametrize("horizon", [1, 7, 14])
def test_features_at_origin_do_not_depend_on_later_data(
    prices: pd.DataFrame, weather: pd.DataFrame, horizon: int
) -> None:
    """Features for origins <= T are identical whether built with asof=T or a later asof."""
    t = pd.Timestamp("2025-06-30")
    early = build_features(prices, weather, t.date(), horizon)
    late = build_features(prices, weather, date(2026, 9, 30), horizon)
    key = ["commodity", "market", "variety", "origin_date"]
    late = late[pd.to_datetime(late["origin_date"]) <= t]
    feats = [c for c in FEATURE_COLUMNS if c not in key]

    def norm(df: pd.DataFrame) -> pd.DataFrame:
        out = df.astype({k: str for k in key[:3]}).set_index(key)[feats].sort_index()
        return out.astype({c: float for c in feats if c not in key})

    a, b = norm(early), norm(late)
    assert len(a) == len(b) > 1000
    pd.testing.assert_frame_equal(a, b)


def test_target_is_log1p_price_at_origin_plus_h(prices: pd.DataFrame) -> None:
    h = 7
    f = build_features(prices, pd.DataFrame(), date(2026, 9, 30), h)
    row = f.dropna(subset=[TARGET]).iloc[500]
    assert pd.Timestamp(row["target_date"]) == pd.Timestamp(row["origin_date"]) + timedelta(days=h)
    actual = prices[
        (prices["market"] == row["market"])
        & (prices["variety"] == row["variety"])
        & (pd.to_datetime(prices["date"]) == pd.Timestamp(row["target_date"]))
    ]["modal_price"].iloc[0]
    assert row[TARGET] == pytest.approx(np.log1p(actual))


def test_target_never_filled_and_unknown_after_asof(prices: pd.DataFrame) -> None:
    asof = date(2026, 9, 30)
    f = build_features(prices, pd.DataFrame(), asof, 14)
    future = pd.to_datetime(f["target_date"]) > pd.Timestamp(asof)
    assert f.loc[future, TARGET].isna().all()
    # Missing market days: the target is NaN exactly where no price was observed.
    observed = set(
        zip(prices["market"], prices["variety"], pd.to_datetime(prices["date"]), strict=True)
    )
    known = f[~future]
    has_obs = [
        (m, v, pd.Timestamp(d)) in observed
        for m, v, d in zip(known["market"], known["variety"], known["target_date"], strict=True)
    ]
    assert (known[TARGET].notna().to_numpy() == np.array(has_obs)).all()
    assert (~np.array(has_obs)).sum() > 0  # the check is not vacuous


def test_prediction_row_exists_for_each_live_series(prices: pd.DataFrame) -> None:
    asof = date(2026, 9, 30)
    f = build_features(prices, pd.DataFrame(), asof, 7)
    pred = f[pd.to_datetime(f["origin_date"]) == pd.Timestamp(asof)]
    assert len(pred) == prices.groupby(["commodity", "market", "variety"]).ngroups
    assert pred[TARGET].isna().all()
    assert (pred["days_since_last_obs"] <= 7).all()


def test_lag_forward_fill_is_capped_at_three_days() -> None:
    days = pd.date_range("2025-01-01", "2025-03-31", freq="D")
    p = pd.DataFrame(
        {
            "date": days,
            "commodity": "banana",
            "market": "Aluva",
            "variety": "Nendran",
            "modal_price": 5000.0,
            "min_price": 4900.0,
            "max_price": 5100.0,
            "n_reports": 1,
        }
    )
    gap = (p["date"] >= "2025-03-10") & (p["date"] <= "2025-03-15")  # 6 missing days
    p = p[~gap]
    f = build_features(p, pd.DataFrame(), date(2025, 3, 31), 1)
    row = f[pd.to_datetime(f["origin_date"]) == pd.Timestamp("2025-03-14")].iloc[0]
    assert np.isnan(row["lag_1_rel"])  # 5 days stale > 3-day carry limit
    assert row["days_since_last_obs"] == 5
    assert row["log_last"] == pytest.approx(np.log1p(5000))  # naive still has a value


def test_festival_and_calendar_flags() -> None:
    days = pd.date_range("2026-07-01", "2026-09-30", freq="D")
    p = pd.DataFrame(
        {
            "date": days,
            "commodity": "banana",
            "market": "Aluva",
            "variety": "Nendran",
            "modal_price": 5000.0,
            "min_price": np.nan,
            "max_price": np.nan,
            "n_reports": 1,
        }
    )
    f = build_features(
        p, pd.DataFrame(), date(2026, 9, 30), 1, [Series("banana", "Aluva", "Nendran")]
    )
    by_target = f.set_index(pd.to_datetime(f["target_date"]))
    assert by_target.loc["2026-08-26", "fest_onam"] == 1  # Thiruvonam 2026
    assert by_target.loc["2026-08-12", "fest_onam"] == 1  # 14 days before
    assert by_target.loc["2026-08-11", "fest_onam"] == 0
    assert by_target.loc["2026-08-27", "fest_onam"] == 0
    assert by_target.loc["2026-08-26", "monsoon"] == 1
    assert np.isnan(by_target.loc["2026-08-26", "spread"])  # modal-only data -> no spread
