"""Parsing of saved API responses (no network)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from cropcast.ingest.agmarknet import (
    STANDARD_COLUMNS,
    parse_datagov,
    parse_portal_daily,
    parse_portal_month,
)
from cropcast.ingest.mappings import normalize
from cropcast.ingest.weather import parse_openmeteo
from cropcast.validate.schemas import validate
from tests.conftest import load_fixture


def test_parse_datagov_sample() -> None:
    payload = load_fixture("agmarknet_sample.json")
    df = parse_datagov(payload["records"])
    assert list(df.columns) == STANDARD_COLUMNS
    assert set(df["state"]) == {"Kerala"}  # Tamil Nadu row filtered at ingest
    assert len(df) == 5
    assert set(df["date"]) == {date(2026, 10, 3)}  # dd/mm/yyyy parsed
    assert df["modal_price"].dtype == float
    assert set(df["source"]) == {"agmarknet"}
    rubber = df.loc[df["commodity"] == "Rubber"].iloc[0]
    assert (rubber["min_price"], rubber["max_price"], rubber["modal_price"]) == (
        18200,
        18500,
        18400,
    )


def test_parse_datagov_handles_x0020_keys() -> None:
    rec = {
        "State": "Kerala",
        "District": "Kottayam",
        "Market": "Kottayam",
        "Commodity": "Rubber",
        "Variety": "RSS-4",
        "Arrival_Date": "02/10/2026",
        "Min_x0020_Price": "18000",
        "Max_x0020_Price": "18300",
        "Modal_x0020_Price": "18100",
    }
    df = parse_datagov([rec])
    assert df.loc[0, "date"] == date(2026, 10, 2)
    assert df.loc[0, "modal_price"] == 18100.0


def test_parse_portal_daily_sample() -> None:
    payload = load_fixture("agmarknet_v2_daily_sample.json")
    df = parse_portal_daily(payload, date(2026, 10, 1))
    assert list(df.columns) == STANDARD_COLUMNS
    assert set(df["date"]) == {date(2026, 10, 1)}
    # Coriander is priced per bundle -> skipped, never mixed into Rs./quintal data.
    assert "Coriander(Leaves)" not in set(df["commodity"])
    assert {"Banana", "Rubber", "Black pepper", "Tapioca", "Onion"} <= set(df["commodity"])
    assert set(df["source"]) == {"agmarknet_v2"}


def test_portal_daily_end_to_end_normalize_validate() -> None:
    payload = load_fixture("agmarknet_v2_daily_sample.json")
    raw = parse_portal_daily(payload, date(2026, 10, 1))
    prices = normalize(raw)
    assert set(prices["commodity"]) == {"banana", "rubber", "pepper", "coconut", "tapioca"}
    assert prices["district"].notna().all()
    good, rejected = validate(prices, today=date(2026, 10, 4))
    assert len(good) + len(rejected) == len(prices)
    assert len(good) > 0


def test_parse_portal_month_sample() -> None:
    payload = load_fixture("agmarknet_v2_month_sample.json")
    df = parse_portal_month(payload, "Banana")
    assert list(df.columns) == STANDARD_COLUMNS
    assert df["date"].notna().all()
    assert min(df["date"]) >= date(2018, 1, 1) and max(df["date"]) <= date(2018, 1, 31)
    assert set(df["commodity"]) == {"Banana"}
    assert (df["modal_price"] > 0).all()


def test_parse_openmeteo_multi_location() -> None:
    item = {
        "daily": {
            "time": ["2026-10-01", "2026-10-02"],
            "precipitation_sum": [12.0, 3.2],
            "temperature_2m_max": [33.8, 31.1],
            "temperature_2m_min": [25.4, 24.5],
            "temperature_2m_mean": [27.5, 27.4],
        }
    }
    df = parse_openmeteo([item, item], ["Kollam", "Kottayam"])
    assert len(df) == 4
    assert set(df["district"]) == {"Kollam", "Kottayam"}
    assert df.loc[0, "rainfall_mm"] == 12.0
    assert isinstance(df.loc[0, "date"], date)
    assert not pd.isna(df["temp_mean_c"]).any()


def test_frozen_sample_prices_fixture() -> None:
    from tests.conftest import FIXTURES

    df = pd.read_parquet(FIXTURES / "sample_prices.parquet")
    assert set(df["commodity"]) == {"banana", "coconut", "rubber", "pepper", "tapioca"}
    assert df.groupby(["commodity", "market", "variety"]).ngroups == 6
    assert (df["date"].max() - df["date"].min()).days >= 700
    assert not df.duplicated(["date", "market", "commodity", "variety"]).any()
    assert (df["modal_price"] > 0).all()


def test_all_sources_failing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from cropcast.ingest import agmarknet

    def down(*_a: object, **_k: object) -> dict[str, object]:
        raise RuntimeError("portal down")

    monkeypatch.setattr(agmarknet, "fetch_portal_daily", down)
    monkeypatch.setattr(agmarknet.settings, "ingest_sources", ["agmarknet", "datagov"])
    # data.gov.in only serves today: a past run date makes the fallback fail too.
    with pytest.raises(RuntimeError, match="all ingest sources failed"):
        agmarknet.fetch_kerala_prices(date(2026, 1, 1), lookback_days=0)


def test_arrivals_parsed_in_tonnes() -> None:
    daily = parse_portal_daily(load_fixture("agmarknet_v2_daily_sample.json"), date(2026, 10, 1))
    assert daily["arrivals_tonnes"].notna().all() and (daily["arrivals_tonnes"] > 0).all()
    month = parse_portal_month(load_fixture("agmarknet_v2_month_sample.json"), "Banana")
    assert month["arrivals_tonnes"].notna().all()
    dg = parse_datagov(load_fixture("agmarknet_sample.json")["records"])
    assert dg["arrivals_tonnes"].isna().all()  # data.gov.in publishes no arrivals
