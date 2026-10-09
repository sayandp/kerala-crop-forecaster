"""Per-crop split-conformal band calibration (display only)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from cropcast.models import calibration as cal


def test_offset_is_the_finite_sample_conformal_quantile() -> None:
    s = pd.Series(np.arange(1, 101, dtype=float))  # 1..100
    # ceil(101 * 0.8) / 100 = 0.81 -> 81st smallest
    assert cal.offset(s) == 81.0
    assert cal.offset(pd.Series([1.0] * 5)) == 0.0  # too few scores: no adjustment


def test_band_widens_when_too_narrow_and_narrows_when_too_wide() -> None:
    rng = np.random.default_rng(1)
    y = pd.Series(np.exp(rng.normal(np.log(100), 0.10, 400)))
    narrow_lo, narrow_hi = pd.Series([98.0] * 400), pd.Series([102.0] * 400)
    wide_lo, wide_hi = pd.Series([50.0] * 400), pd.Series([200.0] * 400)
    for lo, hi in ((narrow_lo, narrow_hi), (wide_lo, wide_hi)):
        q = cal.offset(cal.scores(lo, hi, y))
        new_lo, new_hi = cal.apply(lo, hi, q)
        cov = ((new_lo <= y) & (y <= new_hi)).mean()
        assert 0.78 <= cov <= 0.84
    assert cal.offset(cal.scores(wide_lo, wide_hi, y)) < 0  # narrowing


def test_rolling_calibration_uses_only_matured_past_forecasts() -> None:
    rows = []
    for fold, start in ((1, "2026-01-01"), (2, "2026-01-15")):
        for i in range(14):
            o = pd.Timestamp(start) + pd.Timedelta(days=i)
            rows.append(
                {
                    "crop": "tomato",
                    "horizon": 7,
                    "fold": fold,
                    "origin_date": o,
                    "target_date": o + pd.Timedelta(days=7),
                    "lo": 90.0,
                    "hi": 110.0,
                    "naive": 100.0,
                    "actual": 100.0 if fold == 1 else 150.0,
                }
            )
    band = pd.DataFrame(rows)
    out = cal.rolling_calibrate(band)
    # fold 2 may only use fold-1 forecasts whose target (origin + 7) is before 2026-01-15
    f2 = out[out["fold"] == 2]
    assert (f2["n_cal"] == 7).all()
    # fold 2's own (bad) outcomes never leak into its calibration: offset from fold 1 only
    assert (f2["q"] == 0.0).all()  # 7 < MIN_SCORES -> no adjustment


def test_predict_applies_per_crop_offsets_only_to_that_crop() -> None:
    from cropcast.predict.batch import calibrate_band

    rows = pd.DataFrame(
        {"commodity": ["onion", "onion"], "market": ["Kayamkulam"] * 2, "variety": ["Small", "Big"]}
    )
    pred = pd.DataFrame({"p10": [90.0, 90.0], "p50": [100.0, 100.0], "p90": [110.0, 110.0]})
    calibrate_band(rows, pred, {"small_onion": 0.1})
    assert pred.loc[0, "p10"] == np.expm1(np.log1p(90.0) - 0.1)
    assert pred.loc[0, "p90"] == np.expm1(np.log1p(110.0) + 0.1)
    assert pred.loc[1].tolist() == [90.0, 100.0, 110.0]  # onion (big): no offset
