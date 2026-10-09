"""Champion / challenger gate. Every decision goes to MLflow AND the promotion_log table.

* Price models (`cropcast-price-h{h}`): a challenger is promoted only if, on the 52-fold
  walk-forward diagnostic, it beats the champion (naive) by >= 3 % relative MAPE AND the
  Diebold-Mariano test (APE loss, HAC lag h-1) gives p < 0.05 in its favour.
* Move model (`cropcast-move-h7`): NEVER promoted from a backtest. Only the live evaluation in
  reports/preregistration_e4a.md can set its per-crop `champion_<crop>` alias.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import mlflow
import pandas as pd
from mlflow import MlflowClient
from sqlalchemy import Engine, text

from cropcast.experiments.harness import MAX_P_VALUE, MIN_REL_IMPROVEMENT, score

log = logging.getLogger(__name__)

REGISTRY_EXPERIMENT = "cropcast-registry"


def price_model_name(horizon: int) -> str:
    return f"cropcast-price-h{horizon}"


MOVE_MODEL = "cropcast-move-h7"


@dataclass
class Decision:
    model_name: str
    scope: str
    decision: str  # promote | refuse | refresh | pass | fail | insufficient data
    reason: str
    challenger_version: str | None = None
    champion_version: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


def price_gate(
    predictions: pd.DataFrame,
    horizon: int,
    challenger: str = "lgbm",
    champion: str = "naive",
) -> Decision:
    """Gate on 52-fold diagnostic predictions (models `challenger` and `champion`)."""
    sc = score(predictions, challenger, reference=champion, horizon=horizon)
    a = sc[sc["crop"] == "all"].iloc[0]
    rel, p, stat = float(a["rel_improvement_pct"]), float(a["dm_p"]), float(a["dm_stat"])
    ok = rel >= MIN_REL_IMPROVEMENT and stat < 0 and p < MAX_P_VALUE
    reason = (
        f"52-fold h={horizon}: MAPE {a[f'mape_{challenger}']:.3f} vs {champion} "
        f"{a[f'mape_{champion}']:.3f} ({rel:+.2f} %), DM p={p:.3g} -> "
        + ("meets" if ok else "does not meet")
        + f" the gate (>= {MIN_REL_IMPROVEMENT} % and p < {MAX_P_VALUE})"
    )
    per_crop = {
        r["crop"]: {"rel_pct": r["rel_improvement_pct"], "dm_p": r["dm_p"]}
        for r in sc.to_dict("records")
    }
    return Decision(
        price_model_name(horizon),
        "all",
        "promote" if ok else "refuse",
        reason,
        metrics={"rel_improvement_pct": rel, "dm_p": p, "dm_stat": stat, "per_crop": per_crop},
    )


# Per-crop guard (documented rule change 2026-10-09, effective from the first routine Sunday
# retrain on/after 2026-10-11; not retroactive): when a horizon's LightGBM challenger is promoted,
# any crop (product key) for which it is SIGNIFICANTLY WORSE than naive on the same 52-fold
# diagnostic (DM p < 0.05, challenger loss higher) keeps the naive point forecast.
CROP_GUARD_FROM = date(2026, 10, 11)
NAIVE_ROUTED_TAG = "naive_routed"


def crop_guard(
    predictions: pd.DataFrame, horizon: int, challenger: str = "lgbm", champion: str = "naive"
) -> dict[str, dict[str, float]]:
    """Crops (product keys) where `challenger` is significantly worse than `champion`."""
    from cropcast.bot.names import crop_of  # product keys (config/series.yaml `crop:`)

    by_product = predictions.assign(
        commodity=[
            crop_of(str(c), str(m), str(v))
            for c, m, v in zip(
                predictions["commodity"], predictions["market"], predictions["variety"], strict=True
            )
        ]
    )
    sc = score(by_product, challenger, reference=champion, horizon=horizon)
    worse = sc[(sc["crop"] != "all") & (sc["dm_stat"] > 0) & (sc["dm_p"] < MAX_P_VALUE)]
    return {
        str(r["crop"]): {"rel_pct": float(r["rel_improvement_pct"]), "dm_p": float(r["dm_p"])}
        for r in worse.to_dict("records")
    }


def set_alias(client: MlflowClient, name: str, alias: str, version: str) -> None:
    client.set_registered_model_alias(name, alias, version)
    log.info("alias set", extra={"model": name, "alias": alias, "version": version})


def alias_version(client: MlflowClient, name: str, alias: str) -> str | None:
    try:
        return str(client.get_model_version_by_alias(name, alias).version)
    except Exception:  # alias or model does not exist yet
        return None


def record(engine: Engine | None, decision: Decision, run_id: int | None = None) -> str | None:
    """Log the decision to MLflow (experiment cropcast-registry) and promotion_log."""
    mlflow_run_id = None
    if mlflow.get_tracking_uri():
        mlflow.set_experiment(REGISTRY_EXPERIMENT)
        name = f"gate-{decision.model_name}-{decision.scope}-{datetime.now():%Y%m%d-%H%M%S}"
        with mlflow.start_run(run_name=name, nested=mlflow.active_run() is not None) as run:
            mlflow.set_tags(
                {
                    "model_name": decision.model_name,
                    "scope": decision.scope,
                    "decision": decision.decision,
                }
            )
            mlflow.log_params(
                {
                    "challenger_version": decision.challenger_version,
                    "champion_version": decision.champion_version,
                    "reason": decision.reason[:500],
                }
            )
            mlflow.log_dict(decision.metrics, "decision_metrics.json")
            mlflow_run_id = run.info.run_id
    if engine is not None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO promotion_log (model_name, scope, challenger_version, "
                    "champion_version, decision, reason, metrics, mlflow_run_id, run_id) "
                    "VALUES (:m, :s, :cv, :pv, :d, :r, CAST(:x AS JSONB), :mr, :run)"
                ),
                {
                    "m": decision.model_name,
                    "s": decision.scope,
                    "cv": decision.challenger_version,
                    "pv": decision.champion_version,
                    "d": decision.decision,
                    "r": decision.reason,
                    "x": json.dumps(decision.metrics, default=str),
                    "mr": mlflow_run_id,
                    "run": run_id,
                },
            )
    log.info(
        "gate decision",
        extra={
            "model": decision.model_name,
            "scope": decision.scope,
            "decision": decision.decision,
            "reason": decision.reason,
        },
    )
    return mlflow_run_id
