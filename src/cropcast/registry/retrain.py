"""Weekly retrain -> register -> gate (pipeline step `retrain`, Sunday runs).

For each horizon h in {1, 7, 14} (`cropcast-price-h{h}`):
  * fit LightGBM quantile models (p10/p50/p90) on all data;
  * register the NAIVE champion (p50 = last price, band = LGBM p10/p90) -> alias `champion`
    (decision "refresh": the point forecast is unchanged, only the band is refit);
  * register the LGBM challenger (p50 = LGBM) -> alias `challenger`;
  * 5-fold backtest -> band coverage logged on the versions;
  * 52-fold diagnostic -> price gate; only a "promote" moves `champion` to the challenger.
Move model `cropcast-move-h7`: fit the pre-registered spec, register -> alias `challenger`.
It is never promoted here (only by the live check, see promote.py).
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

import mlflow
from mlflow import MlflowClient
from sqlalchemy import Engine

from cropcast.features.build import FEATURE_COLUMNS, TARGET
from cropcast.features.series import SERIES_PATH, load_series
from cropcast.models.backtest import metrics_table, run_backtest
from cropcast.models.lgbm import LGBMForecaster
from cropcast.models.move import MoveClassifier, spec, spec_hash
from cropcast.models.training import HORIZONS, prepare_features
from cropcast.registry.promote import (
    MOVE_MODEL,
    REGISTRY_EXPERIMENT,
    Decision,
    alias_version,
    price_gate,
    price_model_name,
    record,
    set_alias,
)
from cropcast.registry.pyfunc import MoveModel, PriceModel
from cropcast.tracking import configure_mlflow

log = logging.getLogger(__name__)

PIP = ["lightgbm", "pandas", "numpy", "mlflow"]
GATE_FOLDS = 52


def _register(
    client: MlflowClient,
    name: str,
    python_model: Any,
    artifacts: dict[str, str],
    tags: dict[str, str],
) -> str:
    info = mlflow.pyfunc.log_model(
        name=name.replace("cropcast-", ""),
        python_model=python_model,
        artifacts=artifacts,
        registered_model_name=name,
        pip_requirements=PIP,
    )
    version = str(info.registered_model_version)
    for k, v in tags.items():
        client.set_model_version_tag(name, version, k, v)
    return version


def retrain_and_register(engine: Engine, run_date: date, run_id: int | None) -> dict[str, Any]:
    t0 = time.monotonic()
    configure_mlflow()
    mlflow.set_experiment(REGISTRY_EXPERIMENT)
    client = MlflowClient()
    series = load_series()
    snap, feats = prepare_features(engine, series, run_date)
    out: dict[str, Any] = {"data_to": str(snap.last_date)}
    with (
        mlflow.start_run(run_name=f"retrain-{run_date}") as parent,
        tempfile.TemporaryDirectory() as tmp,
    ):
        d = Path(tmp)
        (d / "features.json").write_text(json.dumps(list(FEATURE_COLUMNS)), encoding="utf-8")
        mlflow.log_artifact(str(SERIES_PATH), artifact_path="config")
        for h in HORIZONS:
            name = price_model_name(h)
            known = feats[h].dropna(subset=[TARGET])
            model = LGBMForecaster(h).fit(known)
            paths = {p.stem.rsplit("_", 1)[-1]: str(p) for p in model.save(d / f"h{h}")}
            band = {"p10": paths["p10"], "p90": paths["p90"], "features": str(d / "features.json")}
            full = {**band, "p50": paths["p50"]}
            # Band coverage on the official 5-fold backtest (the band is the same for both).
            bt = run_backtest({h: feats[h]}, snap.prices, snap.last_date).predictions
            m5 = metrics_table(bt, []).set_index("model")
            coverage = float(m5["coverage_80"].astype(float)["lgbm"])
            common = {
                "horizon": str(h),
                "data_to": str(snap.last_date),
                "band_coverage_80_5fold": f"{coverage:.1f}",
            }
            champ_v = _register(
                client, name, PriceModel("naive"), band, {**common, "point": "naive"}
            )
            chall_v = _register(client, name, PriceModel("lgbm"), full, {**common, "point": "lgbm"})
            prev = alias_version(client, name, "champion")
            set_alias(client, name, "champion", champ_v)
            set_alias(client, name, "challenger", chall_v)
            record(
                engine,
                Decision(
                    name,
                    "all",
                    "refresh",
                    f"weekly refresh: naive point, LGBM band refit (5-fold "
                    f"p10-p90 coverage {coverage:.1f} %)",
                    challenger_version=champ_v,
                    champion_version=prev,
                    metrics={"coverage_80_5fold": coverage},
                ),
                run_id,
            )
            # Gate: LGBM p50 vs naive on the 52-fold diagnostic.
            diag = run_backtest(
                {h: feats[h]}, snap.prices, snap.last_date, n_folds=GATE_FOLDS, quantiles=(0.5,)
            ).predictions
            decision = price_gate(diag, h)
            decision.challenger_version, decision.champion_version = chall_v, champ_v
            record(engine, decision, run_id)
            if decision.decision == "promote":
                set_alias(client, name, "champion", chall_v)
            mlflow.log_metrics(
                {
                    f"h{h}_band_coverage_80": coverage,
                    f"h{h}_gate_rel_pct": decision.metrics["rel_improvement_pct"],
                    f"h{h}_gate_dm_p": decision.metrics["dm_p"],
                }
            )
            out[f"h{h}"] = {
                "champion": alias_version(client, name, "champion"),
                "challenger": chall_v,
                "gate": decision.decision,
                "coverage_80": round(coverage, 1),
            }
        # Move challenger: the pre-registered spec, refit on all data.
        h7 = feats[7].dropna(subset=[TARGET])
        clf = MoveClassifier().fit(h7)
        clf_path = clf.save(d / "move" / "classifier.txt")
        sh = spec_hash(series)
        (d / "spec.json").write_text(
            json.dumps(spec(series), indent=1, default=str), encoding="utf-8"
        )
        mv = _register(
            client,
            MOVE_MODEL,
            MoveModel(),
            {
                "classifier": str(clf_path),
                "features": str(d / "features.json"),
                "spec": str(d / "spec.json"),
            },
            {
                "spec_hash": sh,
                "data_to": str(snap.last_date),
                "best_iteration": str(clf.best_iteration),
            },
        )
        set_alias(client, MOVE_MODEL, "challenger", mv)
        out["move"] = {"challenger": mv, "spec_hash": sh}
        out["minutes"] = round((time.monotonic() - t0) / 60, 1)
        mlflow.log_metric("retrain_minutes", out["minutes"])
        out["mlflow_run"] = parent.info.run_id
    log.info("retrain done", extra=out)
    return out
