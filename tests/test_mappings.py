"""Name normalization: one canonical name per commodity / variety / market / district."""

from __future__ import annotations

import logging

import pandas as pd
import pytest

from cropcast.ingest.mappings import canonical_district, canonical_market, normalize


def _raw(commodity: str, variety: str, market: str = "Ernakulam Market") -> dict[str, object]:
    return {
        "date": "2026-10-01",
        "state": "Keralam",
        "district": None,
        "market": market,
        "commodity": commodity,
        "variety": variety,
        "min_price": 1.0,
        "max_price": 3.0,
        "modal_price": 2.0,
        "source": "test",
    }


@pytest.mark.parametrize(
    ("commodity", "variety", "exp_commodity", "exp_variety"),
    [
        ("Banana", "Nendra Bale", "banana", "Nendran"),
        ("Banana", "Banana - Ripe", "banana", "Ripe"),
        ("Banana - Green", "Banana - Green", "banana", "Green"),
        ("Banana - Green", "Nendra Bale", "banana", "Green Nendran"),
        ("Coconut", "Big", "coconut", "Big"),
        ("Rubber", "RSS-4", "rubber", "RSS-4"),
        ("Black pepper", "Ungrabled", "pepper", "Ungarbled"),
        ("Pepper garbled", "Other", "pepper", "Garbled Other"),
        ("Tapioca", "Other", "tapioca", "Other"),
        ("  TAPIOCA ", "", "tapioca", "Other"),
    ],
)
def test_commodity_and_variety_mapping(
    commodity: str, variety: str, exp_commodity: str, exp_variety: str
) -> None:
    out = normalize(pd.DataFrame([_raw(commodity, variety)]))
    assert out.loc[0, "commodity"] == exp_commodity
    assert out.loc[0, "variety"] == exp_variety
    assert out.loc[0, "state"] == "Kerala"


def test_green_and_ripe_banana_never_share_a_key() -> None:
    out = normalize(pd.DataFrame([_raw("Banana", "Other"), _raw("Banana - Green", "Other")]))
    assert out[["market", "commodity", "variety"]].duplicated().sum() == 0


def test_unmapped_commodities_are_logged_not_silently_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    df = pd.DataFrame(
        [_raw("Banana", "Poovan"), _raw("Cardamom", "Bold"), _raw("Cardamom", "Small")]
    )
    with caplog.at_level(logging.INFO, logger="cropcast.ingest.mappings"):
        out = normalize(df)
    assert list(out["commodity"]) == ["banana"]
    rec = next(r for r in caplog.records if r.getMessage() == "dropping unmapped commodities")
    assert rec.unmapped == {"Cardamom": 2}  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ernakulam Market", "Ernakulam"),
        ("Adimali  VFPCK Market", "Adimali VFPCK"),
        ("Adimali VFPCK Market", "Adimali VFPCK"),
        ("Bharananganam VFPCK", "Bharananganam VFPCK"),
        ("Broadway market Market", "Broadway"),
        ("ARWM Muvattupuzha", "ARWM Muvattupuzha"),
        ("  Kottayam  ", "Kottayam"),
    ],
)
def test_canonical_market(raw: str, expected: str) -> None:
    assert canonical_market(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Thirssur", "Thrissur"),
        ("Kozhikode(Calicut)", "Kozhikode"),
        ("Palakad", "Palakkad"),
        ("Alleppey", "Alappuzha"),
        ("Kasargod", "Kasaragod"),
        (None, None),
    ],
)
def test_canonical_district(raw: str | None, expected: str | None) -> None:
    assert canonical_district(raw) == expected


def test_district_is_filled_from_market_lookup() -> None:
    out = normalize(pd.DataFrame([_raw("Banana", "Poovan", market="Adimali VFPCK Market")]))
    assert out.loc[0, "district"] == "Idukki"
