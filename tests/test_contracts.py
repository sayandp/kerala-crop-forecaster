"""Pandera data-contract tests: the good path and every failure case."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from cropcast.validate.schemas import RejectRateExceeded, check_reject_rate, validate
from tests.conftest import price_row

TODAY = date(2026, 10, 3)


def _validate(rows: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    return validate(pd.DataFrame(rows), today=TODAY)


def test_good_rows_pass(good_prices: pd.DataFrame) -> None:
    good, rejected = validate(good_prices, today=TODAY)
    assert len(good) == len(good_prices)
    assert rejected.empty
    assert isinstance(good.loc[0, "date"], date)


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"modal_price": 0.0, "min_price": 0.0}, "modal_price:modal_price_not_positive"),
        ({"modal_price": -10.0, "min_price": -20.0}, "modal_price:modal_price_not_positive"),
        ({"min_price": 5600.0}, "min_le_modal_le_max"),
        ({"max_price": 5400.0}, "min_le_modal_le_max"),
        ({"date": date(2026, 10, 4)}, "date:future_date"),
        ({"date": "not-a-date"}, "date:missing_value"),
        ({"state": "Tamil Nadu"}, "state:state_not_kerala"),
        ({"commodity": "onion"}, "commodity:unknown_commodity"),
        ({"market": None}, "market:missing_value"),
        ({"variety": None}, "variety:missing_value"),
        ({"modal_price": None}, "modal_price:missing_value"),
    ],
)
def test_each_failure_is_quarantined_with_reason(override: dict[str, Any], reason: str) -> None:
    good, rejected = _validate([price_row(variety="ok"), price_row(**override)])
    assert list(good["variety"]) == ["ok"]
    assert len(rejected) == 1
    assert reason in rejected.loc[0, "reason"].split(";")


def test_duplicate_key_keeps_first_and_rejects_rest() -> None:
    rows = [
        price_row(modal_price=5500.0),
        price_row(modal_price=5800.0),
        price_row(modal_price=5900.0),
    ]
    good, rejected = _validate(rows)
    assert len(good) == 1
    assert good.loc[0, "modal_price"] == 5500.0
    assert list(rejected["reason"]) == ["duplicate_key", "duplicate_key"]


def test_null_district_is_allowed() -> None:
    good, rejected = _validate([price_row(district=None)])
    assert len(good) == 1 and rejected.empty


def test_rows_are_never_silently_dropped() -> None:
    rows = [price_row(variety=str(i), modal_price=float(i)) for i in range(-3, 7)]
    good, rejected = _validate(rows)
    assert len(good) + len(rejected) == len(rows)


def test_reject_rate_gate() -> None:
    assert check_reject_rate(100, 20) == pytest.approx(0.2)
    with pytest.raises(RejectRateExceeded):
        check_reject_rate(100, 21)
    assert check_reject_rate(0, 0) == 0.0
