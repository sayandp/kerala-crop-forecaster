"""Phase 6b crops: pre-registered move spec untouched, selected-markets-only ingest, names."""

from __future__ import annotations

import pandas as pd
import pytest

from cropcast.bot import names
from cropcast.features.series import load_series
from cropcast.ingest.mappings import normalize
from cropcast.models.move import PREREG_SERIES, move_rows, move_series, spec_hash
from cropcast.validate.units import bands


def test_move_classifier_spec_is_unchanged_by_new_series() -> None:
    series = load_series()
    assert len(series) > len(PREREG_SERIES)  # new crops were added ...
    prereg = move_series(series)
    assert len(prereg) == 20
    assert spec_hash(prereg) == "18b80303494e1cc5"  # ... but the pre-registered spec is intact


def test_move_rows_drop_new_series_and_unused_categories() -> None:
    df = pd.DataFrame(
        {
            "commodity": pd.Categorical(["pepper", "tomato"]),
            "market": pd.Categorical(["Kannur", "Kayamkulam"]),
            "variety": pd.Categorical(["Other", "Other"]),
        }
    )
    out = move_rows(df)
    assert out["commodity"].tolist() == ["pepper"]
    assert list(out["commodity"].cat.categories) == ["pepper"]


def _raw(commodity: str, market: str, variety: str = "Other") -> dict[str, object]:
    return {
        "date": "2026-10-08",
        "state": "Keralam",
        "district": None,
        "market": market,
        "commodity": commodity,
        "variety": variety,
        "min_price": 1000.0,
        "max_price": 1200.0,
        "modal_price": 1100.0,
        "source": "test",
    }


def test_ingest_keeps_only_selected_markets_for_new_crops() -> None:
    raw = pd.DataFrame(
        [
            _raw("Tomato", "Kayamkulam"),  # selected
            _raw("Tomato", "Kannur"),  # not selected -> dropped
            _raw("Onion", "Palakkad", "Small"),  # selected (small onion)
            _raw("Cucumbar(Kheera)", "Payyannur"),  # selected (name mapped)
            _raw("Tapioca", "Kannur"),  # original crop: every market kept
            _raw("Cardamom", "Thodupuzha"),  # not a target crop
        ]
    )
    out = normalize(raw)
    got = set(zip(out["commodity"], out["market"], strict=True))
    assert got == {
        ("tomato", "Kayamkulam"),
        ("onion", "Palakkad"),
        ("cucumber", "Payyannur"),
        ("tapioca", "Kannur"),
    }


def test_every_series_commodity_has_a_units_band() -> None:
    assert {s.commodity for s in load_series()} <= set(bands())


@pytest.mark.parametrize(
    ("typed", "crop"),
    [
        ("ഇഞ്ചി", "ginger"),
        ("അടയ്ക്ക", "arecanut"),
        ("പാക്ക്", "arecanut"),
        ("കാപ്പി", "coffee"),
        ("തക്കാളി", "tomato"),
        ("സവാള", "onion"),
        ("ചെറിയ ഉള്ളി", "small_onion"),
        ("shallot", "small_onion"),
        ("പച്ചമുളക്", "green_chilli"),
        ("പാവയ്ക്ക", "bitter_gourd"),
        ("മുരിങ്ങക്കായ", "drumstick"),
        ("വെള്ളരി", "cucumber"),
        ("പാളയങ്കോടൻ", "palayankodan"),
        ("പൂവൻ", "poovan"),
        ("nendran", "banana"),
    ],
)
def test_new_crop_names(typed: str, crop: str) -> None:
    assert names.match_crop(typed) == crop


def test_products_sharing_a_market_are_distinct() -> None:
    small = names.markets_of("small_onion")
    big = names.markets_of("onion")
    assert {s.market for s in small} == {"Kayamkulam", "Palakkad"}
    assert [(s.market, s.variety) for s in big] == [("Kayamkulam", "Big")]
    assert names.crop_of("banana", "Kayamkulam", "Palayamthodan") == "palayankodan"
    assert names.crop_of("banana", "Kayamkulam", "Nendran") == "banana"
    assert set(names.CROPS) == {s.key for s in names.served()}


def test_deep_link_with_underscore_crop_key() -> None:
    kind, crop, s = names.parse_start_payload("alert_small_onion_palakkad") or ("", "", None)
    assert (kind, crop, s and (s.market, s.variety)) == (
        "alert",
        "small_onion",
        ("Palakkad", "Small"),
    )
    assert names.parse_start_payload("price_green_chilli") == ("price", "green_chilli", None)
    assert names.parse_start_payload("alert_onion_kayamkulam")[1] == "onion"  # type: ignore[index]


def _diag(crop_series: dict[tuple[str, str, str], float], n_dates: int = 120) -> pd.DataFrame:
    """52-fold-like predictions: per series, lgbm error = naive error * factor (+ noise)."""
    import numpy as np

    rng = np.random.default_rng(0)
    rows = []
    for (c, m, v), factor in crop_series.items():
        for i in range(n_dates):
            d = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)
            actual = 100.0
            naive_err = abs(rng.normal(5, 1))
            for model, err in (
                ("naive", naive_err),
                ("lgbm", naive_err * factor + rng.normal(0, 0.1)),
            ):
                rows.append(
                    {
                        "commodity": c,
                        "market": m,
                        "variety": v,
                        "target_date": d,
                        "horizon": 14,
                        "fold": 1,
                        "model": model,
                        "actual": actual,
                        "pred": actual + err,
                    }
                )
    return pd.DataFrame(rows)


def test_crop_guard_routes_only_significantly_worse_products() -> None:
    from cropcast.registry.promote import CROP_GUARD_FROM, crop_guard

    diag = _diag(
        {
            ("onion", "Kayamkulam", "Small"): 1.5,  # small onion: LGBM clearly worse
            ("onion", "Kayamkulam", "Big"): 0.8,  # onion (big): LGBM better
            ("coffee", "Kalpetta", "Other"): 1.0,  # tie
        }
    )
    routed = crop_guard(diag, horizon=14)
    assert set(routed) == {"small_onion"} and routed["small_onion"]["dm_p"] < 0.05
    assert routed["small_onion"]["rel_pct"] < 0
    assert CROP_GUARD_FROM.isoformat() == "2026-10-11"  # documented effective date


def test_route_naive_serves_last_price_with_the_same_band() -> None:
    from cropcast.predict.batch import route_naive

    rows = pd.DataFrame(
        {
            "commodity": ["onion", "onion"],
            "market": ["Kayamkulam"] * 2,
            "variety": ["Small", "Big"],
            "last_value": [5000.0, 3000.0],
        }
    )
    pred = pd.DataFrame({"p10": [4600.0, 2700.0], "p50": [5200.0, 3100.0], "p90": [5400.0, 3300.0]})
    mask = route_naive(rows, pred, {"small_onion"})
    assert mask.tolist() == [True, False]
    assert pred.loc[0].tolist() == [4600.0, 5000.0, 5400.0]  # naive point, band unchanged
    assert pred.loc[1].tolist() == [2700.0, 3100.0, 3300.0]  # other crops untouched
