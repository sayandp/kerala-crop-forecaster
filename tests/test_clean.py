"""Clean layer: same-day aggregation, duplicate eligibility, alias guard + application."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from cropcast.clean.aliases import AliasCandidate, apply_aliases, evaluate_candidates
from cropcast.clean.build import aggregate_same_day, build_clean, eligible_duplicates
from tests.conftest import price_row

SWITCH = date(2025, 11, 7)


def _clean_row(**kw: Any) -> dict[str, Any]:
    r = price_row(**kw)
    return {
        k: r[k]
        for k in (
            "commodity",
            "market",
            "variety",
            "date",
            "min_price",
            "max_price",
            "modal_price",
            "source",
        )
    }


def test_same_day_duplicates_are_aggregated() -> None:
    df = pd.DataFrame(
        [
            _clean_row(min_price=1300.0, max_price=1500.0, modal_price=1400.0, source="a"),
            _clean_row(min_price=2300.0, max_price=2500.0, modal_price=2400.0, source="b"),
            _clean_row(min_price=None, max_price=None, modal_price=2000.0, source="a"),
            _clean_row(variety="Poovan", modal_price=5200.0),  # different series, untouched
        ]
    )
    out = aggregate_same_day(df).set_index("variety")
    nendran = out.loc["Nendran"]
    assert nendran["modal_price"] == 2000.0  # median of 1400, 2400, 2000
    assert nendran["min_price"] == 1300.0  # min of mins, NULLs skipped
    assert nendran["max_price"] == 2500.0  # max of maxes
    assert nendran["n_reports"] == 3
    assert nendran["sources"] == "a,b"
    assert out.loc["Poovan", "n_reports"] == 1


def test_all_modal_only_reports_keep_null_bounds() -> None:
    df = pd.DataFrame([_clean_row(min_price=None, max_price=None)] * 2)
    out = aggregate_same_day(df)
    assert out.loc[0, ["min_price", "max_price"]].isna().all()


def test_eligible_duplicates_collapse_repeats_and_drop_bad_rows() -> None:
    grade2 = price_row(min_price=2300.0, max_price=2500.0, modal_price=2400.0)
    both = "duplicate_key;min_le_modal_le_max"
    rej = pd.DataFrame(
        [
            {**grade2, "reason": "duplicate_key"},
            {**grade2, "reason": "duplicate_key"},  # re-quarantined on a later run
            {
                **price_row(min_price=0.0, max_price=0.0),
                "reason": "duplicate_key;min_le_modal_le_max",
            },
            {**price_row(modal_price=9000.0), "reason": both},  # modal > max: still bad
            {**price_row(modal_price=0.0, min_price=0.0), "reason": "modal_price_not_positive"},
        ]
    )
    out = eligible_duplicates(rej)
    assert sorted(out["modal_price"]) == [2400.0, 5500.0]  # repeat collapsed, bad ones out
    assert out.loc[out["modal_price"] == 5500.0, "min_price"].isna().all()  # 0/0 -> NULL


# --- aliases ------------------------------------------------------------------------


def _series(market: str, variety: str, start: date, days: int, price: float) -> pd.DataFrame:
    dates = [start + timedelta(days=i) for i in range(days)]
    return pd.DataFrame(
        {
            "date": dates,
            "market": market,
            "commodity": "rubber",
            "variety": variety,
            "modal_price": price,
        }
    )


def _evaluate(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cand = [AliasCandidate("rubber", "Other", "RSS-4")]
    return evaluate_candidates(prices, cand, SWITCH, tolerance=0.10, window_days=30, min_obs=5)


def test_alias_accepted_within_tolerance() -> None:
    prices = pd.concat(
        [
            _series("Kalpetta", "Other", SWITCH - timedelta(days=30), 30, 17400.0),
            _series("Kalpetta", "RSS-4", SWITCH, 30, 17300.0),
        ]
    )
    accepted, decisions = _evaluate(prices)
    assert list(decisions["decision"]) == ["accepted"]
    assert accepted.loc[0, "market"] == "Kalpetta"
    assert accepted.loc[0, "valid_to"] == SWITCH - timedelta(days=1)
    assert accepted.loc[0, "guard_ratio"] == pytest.approx(17400 / 17300 - 1)


def test_alias_rejected_by_ten_percent_guard() -> None:
    prices = pd.concat(
        [
            _series("Kalpetta", "Other", SWITCH - timedelta(days=30), 30, 20000.0),
            _series("Kalpetta", "RSS-4", SWITCH, 30, 17000.0),  # +17.6 %
        ]
    )
    accepted, decisions = _evaluate(prices)
    assert accepted.empty
    assert decisions.loc[0, "decision"].startswith("rejected: price ratio")


def test_alias_rejected_when_both_labels_live_after_switch() -> None:
    prices = pd.concat(
        [
            _series("Pulpally", "Other", SWITCH - timedelta(days=30), 60, 17900.0),
            _series("Pulpally", "RSS-4", SWITCH, 30, 17900.0),
        ]
    )
    accepted, decisions = _evaluate(prices)
    assert accepted.empty and "two products" in decisions.loc[0, "decision"]


def test_alias_rejected_on_insufficient_data() -> None:
    prices = pd.concat(
        [
            _series("Irityy", "Other", SWITCH - timedelta(days=3), 3, 18000.0),
            _series("Irityy", "RSS-4", SWITCH, 30, 18000.0),
        ]
    )
    accepted, decisions = _evaluate(prices)
    assert accepted.empty and "insufficient" in decisions.loc[0, "decision"]


def test_apply_aliases_respects_market_and_dates() -> None:
    aliases = pd.DataFrame(
        [
            {
                "commodity": "rubber",
                "market": "Kalpetta",
                "raw_variety": "Other",
                "canonical_variety": "RSS-4",
                "valid_from": None,
                "valid_to": SWITCH - timedelta(days=1),
                "guard_ratio": 0.006,
            }
        ]
    )
    df = pd.DataFrame(
        [
            {
                "date": SWITCH - timedelta(days=1),
                "market": "Kalpetta",
                "commodity": "rubber",
                "variety": "Other",
            },
            {
                "date": SWITCH + timedelta(days=2),
                "market": "Kalpetta",
                "commodity": "rubber",
                "variety": "Other",
            },  # after valid_to: stray late report keeps its label
            {
                "date": SWITCH - timedelta(days=1),
                "market": "Pulpally",
                "commodity": "rubber",
                "variety": "Other",
            },  # other market: untouched
        ]
    )
    out = apply_aliases(df, aliases)
    assert list(out["variety"]) == ["RSS-4", "Other", "Other"]


def test_build_clean_merges_aliased_rows_into_one_series() -> None:
    raw = pd.DataFrame(
        [
            _clean_row(
                commodity="rubber",
                market="Kalpetta",
                variety="Other",
                date=SWITCH - timedelta(days=1),
                min_price=17000.0,
                max_price=17500.0,
                modal_price=17400.0,
            ),
            _clean_row(
                commodity="rubber",
                market="Kalpetta",
                variety="RSS-4",
                date=SWITCH,
                min_price=17000.0,
                max_price=17500.0,
                modal_price=17300.0,
            ),
        ]
    )
    aliases, _ = _evaluate(
        pd.concat(
            [
                _series("Kalpetta", "Other", SWITCH - timedelta(days=30), 30, 17400.0),
                _series("Kalpetta", "RSS-4", SWITCH, 30, 17300.0),
            ]
        )
    )
    out = build_clean(raw, pd.DataFrame(), aliases)
    assert set(out["variety"]) == {"RSS-4"} and len(out) == 2
    assert np.issubdtype(out["n_reports"].dtype, np.integer)
