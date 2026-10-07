"""Phase 3: pyfunc models, gate, idempotent predict/shadow/notify, pre-registration order,
channel templates, live (pre-registered) verdict logic."""

from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine, text

from cropcast.alerts import channel
from cropcast.config import PROJECT_ROOT
from cropcast.features.build import FEATURE_COLUMNS, TARGET, build_features
from cropcast.features.series import Series
from cropcast.features.snapshot import Snapshot
from cropcast.models.lgbm import LGBMForecaster
from cropcast.models.move import MoveClassifier, spec_hash
from cropcast.monitor import live
from cropcast.predict import batch
from cropcast.registry.promote import price_gate
from cropcast.registry.pyfunc import MoveModel, PriceModel
from tests.conftest import FIXTURES

ASOF = date(2026, 9, 30)


@pytest.fixture(scope="module")
def sample() -> pd.DataFrame:
    return pd.read_parquet(FIXTURES / "sample_prices.parquet").assign(n_reports=1)


@pytest.fixture(scope="module")
def series(sample: pd.DataFrame) -> list[Series]:
    keys = sample[["commodity", "market", "variety"]].drop_duplicates()
    return [Series(*map(str, k)) for k in keys.itertuples(index=False)]


@pytest.fixture(scope="module")
def models(
    tmp_path_factory: pytest.TempPathFactory, sample: pd.DataFrame, series: list[Series]
) -> dict[str, Any]:
    d = tmp_path_factory.mktemp("models")
    feats = build_features(sample, pd.DataFrame(), ASOF, 7, series)
    lg = LGBMForecaster(7).fit(feats.dropna(subset=[TARGET]))
    paths = {p.stem.rsplit("_", 1)[-1]: str(p) for p in lg.save(d)}
    (d / "features.json").write_text(json.dumps(list(FEATURE_COLUMNS)), encoding="utf-8")
    clf = MoveClassifier().fit(feats.dropna(subset=[TARGET]))
    clf_path = clf.save(d / "clf.txt")
    ctx = SimpleNamespace(
        artifacts={**paths, "features": str(d / "features.json"), "classifier": str(clf_path)}
    )
    naive, lgbm, move = PriceModel("naive"), PriceModel("lgbm"), MoveModel()
    for m in (naive, lgbm, move):
        m.load_context(ctx)
    return {"naive": naive, "lgbm": lgbm, "move": move, "features": feats}


# --- pyfunc -----------------------------------------------------------------------------------


def test_naive_pyfunc_returns_last_price_and_interval_contains_p50(models: dict[str, Any]) -> None:
    rows = models["features"].tail(200)
    out = models["naive"].predict(None, rows)
    assert np.allclose(out["p50"], rows["last_value"])
    assert (out["p10"] <= out["p50"]).all() and (out["p50"] <= out["p90"]).all()
    lg = models["lgbm"].predict(None, rows)
    assert (lg["p10"] <= lg["p50"]).all() and (lg["p50"] <= lg["p90"]).all()
    assert np.allclose(out["p10"], np.minimum(lg["p10"], out["p50"]))  # same band


def test_move_pyfunc_probabilities(models: dict[str, Any]) -> None:
    out = models["move"].predict(None, models["features"].tail(50))
    assert np.allclose(out[["p_down", "p_flat", "p_up"]].sum(axis=1), 1.0)
    assert set(out["pred_class"]) <= {"down", "flat", "up"}


# --- gate -------------------------------------------------------------------------------------


def _gate_preds(improvement: float, noise: float, n_dates: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    for i in range(n_dates):
        d = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)
        for s in range(5):
            actual = 1000.0
            naive = actual * (1 + rng.choice([-1, 1]) * 0.05)
            err = 0.05 * (1 - improvement) * (1 + noise * rng.standard_normal())
            chall = actual * (1 + rng.choice([-1, 1]) * abs(err))
            base = {
                "commodity": "banana",
                "market": f"m{s}",
                "variety": "v",
                "target_date": d,
                "actual": actual,
            }
            rows += [
                {**base, "model": "naive", "pred": naive},
                {**base, "model": "lgbm", "pred": chall},
            ]
    return pd.DataFrame(rows)


def test_gate_refuses_without_significance() -> None:
    noisy = price_gate(_gate_preds(0.05, noise=8.0, n_dates=40), horizon=7)
    assert noisy.decision == "refuse"
    # Significant, but below the 3 % bar.
    small = price_gate(_gate_preds(0.02, noise=0.3, n_dates=600), horizon=7)
    assert small.decision == "refuse" and small.metrics["dm_p"] < 0.05
    clear = price_gate(_gate_preds(0.10, noise=0.1), horizon=7)
    assert clear.decision == "promote"


# --- pre-registration -------------------------------------------------------------------------


def _first_commit_time(path: str) -> int | None:
    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%ct", "--", path],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = out.stdout.split()
    return int(lines[-1]) if lines else None


def test_preregistration_committed_before_any_shadow_code() -> None:
    assert (PROJECT_ROOT / batch.PREREG_PATH).exists()
    prereg = _first_commit_time(batch.PREREG_PATH)
    assert prereg is not None, "pre-registration is not committed (shallow clone?)"
    shadow_code = _first_commit_time("src/cropcast/predict/batch.py")
    if shadow_code is not None:  # once committed, the shadow code must be newer
        assert prereg < shadow_code
    assert batch.prereg_commit()


def test_shadow_refuses_without_preregistration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(batch, "prereg_commit", lambda: "")
    with pytest.raises(RuntimeError, match="not committed"):
        batch.predict_shadow(None, None, [], ASOF, None)  # type: ignore[arg-type]


# --- idempotent daily steps (DB) --------------------------------------------------------------


@pytest.mark.db
def test_predict_shadow_notify_idempotent(
    engine: Engine,
    models: dict[str, Any],
    sample: pd.DataFrame,
    series: list[Series],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_load(name: str, alias: str) -> tuple[Any, str]:
        m = models["move"] if "move" in name else models["naive"]
        return SimpleNamespace(predict=lambda df: m.predict(None, df)), "1"

    monkeypatch.setattr(batch, "_load", fake_load)
    monkeypatch.setattr(
        batch,
        "MlflowClient",
        lambda: SimpleNamespace(
            get_model_version=lambda n, v: SimpleNamespace(tags={"spec_hash": spec_hash(series)})
        ),
    )
    snap = Snapshot(sample, pd.DataFrame(), Path("x"), Path("y"))
    for _ in range(2):
        batch.predict_prices(engine, snap, series, ASOF, None)
        batch.predict_shadow(engine, snap, series, ASOF, None)
    with engine.connect() as conn:
        n_fc = conn.execute(text("SELECT count(*) FROM forecasts")).scalar_one()
        n_sh = conn.execute(text("SELECT count(*) FROM shadow_predictions")).scalar_one()
    assert n_fc == 3 * len(series)
    assert n_sh == sum(s.commodity in ("coconut", "pepper", "rubber", "tapioca") for s in series)

    # notify: posts once per date, never twice.
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE channel_posts, prices_clean"))
        conn.execute(
            text(
                "INSERT INTO prices_raw (date, state, market, commodity, variety, "
                "modal_price, source) VALUES (:d, 'Kerala', 'X', 'banana', 'v', 1, 't') "
                "ON CONFLICT DO NOTHING"
            ),
            {"d": ASOF},
        )
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        channel.settings, "telegram_bot_token", SimpleNamespace(get_secret_value=lambda: "t")
    )
    monkeypatch.setattr(channel.settings, "telegram_channel_id", "@test")
    monkeypatch.setattr(channel, "new_data_today", lambda e, d: True)
    monkeypatch.setattr(channel, "postable", lambda rows, d: rows)  # freshness: test_units
    monkeypatch.setattr(
        channel, "_api", lambda m, p: calls.append(p) or {"result": {"message_id": 7}}
    )
    first = channel.notify(engine, ASOF)
    second = channel.notify(engine, ASOF)
    assert first.status == "posted" and second.status == "skipped" and len(calls) == 1


@pytest.mark.db
def test_notify_skips_without_new_data(engine: Engine) -> None:
    res = channel.notify(engine, ASOF + timedelta(days=400), dry_run=True)
    assert res.status == "skipped"


# --- templates --------------------------------------------------------------------------------


def test_templates_render_for_every_crop_both_languages() -> None:
    cfg = channel.channel_config()
    rows = []
    for crop, markets in cfg["crops"].items():
        for i, mk in enumerate(markets):
            rows.append(
                {
                    "commodity": crop,
                    "market": mk["market"],
                    "variety": mk["variety"],
                    "p10": 4000.0,
                    "p90": 5200.0,
                    "last_value": 4600.0,
                    "obs_date": ASOF if i == 0 else ASOF - timedelta(days=2),
                }
            )
    post = channel.render_post(pd.DataFrame(rows), ASOF)
    for lang in channel.LANGS:
        t = channel.template(lang)
        for crop in cfg["crops"]:
            assert t["crops"][crop] in post
    assert "{" not in post and "}" not in post
    assert "₹46" in post and f"₹40{chr(0x2013)}52" in post  # Rs./quintal -> Rs./kg
    assert channel.template("en")["footer"].split(".")[0] in post
    assert "alert" not in post.lower()  # no move alerts in Stage 1


# --- pre-registered live verdict --------------------------------------------------------------


def _shadow(crop: str, days: int, skill: float, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(days):
        d = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        for _s in range(3):
            y = rng.choice(["up", "flat", "down"], p=[0.25, 0.5, 0.25])
            actual = {"up": 1100.0, "flat": 1000.0, "down": 900.0}[y]
            pred = y if rng.random() < skill else rng.choice(["up", "flat", "down"])
            rows.append(
                {
                    "commodity": crop,
                    "target_date": d,
                    "actual": actual,
                    "last_value_f": 1000.0,
                    "pred_class": pred,
                    "trend_class": "flat",
                }
            )
    return pd.DataFrame(rows)


def test_verdict_insufficient_then_pass_then_fail() -> None:
    few = live.shadow_evaluation(_shadow("coconut", 20, 0.9))
    assert set(few["verdict"]) == {"insufficient data"}
    good = live.shadow_evaluation(
        pd.concat(
            [
                _shadow(c, 100, 0.9, i)
                for i, c in enumerate(("coconut", "pepper", "rubber", "tapioca"))
            ]
        )
    )
    assert set(good["verdict"]) == {"pass"}
    bad = live.shadow_evaluation(
        pd.concat(
            [
                _shadow(c, 100, 0.0, i)
                for i, c in enumerate(("coconut", "pepper", "rubber", "tapioca"))
            ]
        )
    )
    assert set(bad["verdict"]) == {"fail"}


def test_holm_adjustment() -> None:
    adj = live.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": float("nan")})
    assert adj["a"] == pytest.approx(0.04)  # 4 x 0.01
    assert adj["c"] == pytest.approx(0.09)  # 3 x 0.03
    assert adj["b"] == pytest.approx(0.09)  # max(0.09, 2 x 0.04)
    assert adj["d"] == 1.0
