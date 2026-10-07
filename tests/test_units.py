"""Unit sanity: plausible Rs./kg bands per crop (config/units.yaml) and unit flags."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
import pytest

from cropcast.alerts import channel
from cropcast.config import settings
from cropcast.ingest.agmarknet import parse_portal_daily
from cropcast.validate.units import bands, implausible
from tests.conftest import FIXTURES


def test_bands_cover_every_target_crop_and_are_ordered() -> None:
    b = bands()
    assert set(b) == set(settings.target_commodities)
    assert all(0 < v["min"] < v["max"] for v in b.values())


@pytest.mark.parametrize("crop", ["banana", "coconut", "pepper", "rubber", "tapioca"])
def test_real_prices_fall_in_plausible_rs_per_kg_band(crop: str) -> None:
    """Frozen real data (2 years): >= 99 % of each crop's modal prices are in its band."""
    df = pd.read_parquet(FIXTURES / "sample_prices.parquet")
    g = df[df["commodity"] == crop]
    assert len(g) > 100
    share_bad = implausible(g["commodity"], g["modal_price"]).mean()
    assert share_bad <= 0.01, f"{crop}: {share_bad:.1%} outside {bands()[crop]} Rs./kg"


def test_per_nut_coconut_price_is_flagged() -> None:
    rows = pd.DataFrame({"commodity": ["coconut", "coconut"], "modal_price": [6500.0, 25.0]})
    assert list(implausible(rows["commodity"], rows["modal_price"])) == [False, True]


def test_coconut_not_reported_per_quintal_is_flagged_and_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = {
        "commodityGroups": [
            {
                "commodities": [
                    {
                        "commodityName": "Coconut",
                        "markets": [
                            {
                                "marketCenter": "Kollam Market",
                                "data": [
                                    {
                                        "variety": "Big",
                                        "minimumPrice": 14.0,
                                        "maximumPrice": 16.0,
                                        "modalPrice": 15.0,
                                        "unitOfPrice": "Rs./Nos",
                                        "arrivals": 1.0,
                                        "unitOfArrivals": "Nos",
                                    },
                                    {
                                        "variety": "Medium",
                                        "minimumPrice": 6000.0,
                                        "maximumPrice": 6600.0,
                                        "modalPrice": 6400.0,
                                        "unitOfPrice": "Rs./Quintal",
                                        "arrivals": 1.0,
                                        "unitOfArrivals": "Metric Tonnes",
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        ]
    }
    with caplog.at_level(logging.WARNING):
        df = parse_portal_daily(payload, date(2026, 10, 1))
    assert list(df["variety"]) == ["Medium"]  # the per-nut row never enters prices
    assert any(r.getMessage() == "target crop not reported per quintal" for r in caplog.records)


def test_notify_leaves_out_stale_and_implausible_markets() -> None:
    run = date(2026, 10, 7)
    rows = pd.DataFrame(
        [
            {
                "commodity": "banana",
                "market": "Kayamkulam",
                "variety": "Nendran",
                "p10": 4500.0,
                "p90": 5800.0,
                "last_value": 5100.0,
                "obs_date": run - timedelta(days=3),
            },
            {
                "commodity": "banana",
                "market": "Parassala",
                "variety": "Nendran",
                "p10": 6300.0,
                "p90": 7400.0,
                "last_value": 7000.0,
                "obs_date": run - timedelta(days=4),
            },  # stale
            {
                "commodity": "rubber",
                "market": "Kalpetta",
                "variety": "RSS-4",
                "p10": 1500.0,
                "p90": 2000.0,
                "last_value": 1800.0,
                "obs_date": run,
            },  # Rs.18/kg: implausible
        ]
    )
    keep = channel.postable(rows, run)
    assert list(keep["market"]) == ["Kayamkulam"]
    post = channel.render_post(keep, run)
    assert "Parassala" not in post and "Kalpetta" not in post
    assert (
        channel.template("en")["crops"]["rubber"] not in post
    )  # crop with no fresh market omitted
    assert "കേരള വിപണി വില" in post and "7 ദിവസത്തിനു ശേഷം പ്രതീക്ഷിക്കാവുന്ന വില" in post
