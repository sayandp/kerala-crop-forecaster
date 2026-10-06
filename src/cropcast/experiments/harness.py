"""Phase 2.5 signal hunt: shared data loading, scoring vs naive (MAPE + Diebold-Mariano),
the decision rule, and MLflow logging (child runs under one parent).

Yardstick: the 52-fold walk-forward diagnostic at h=7 (14-day folds, ~2 years), p50 only.
Decision rule: an approach WINS only if it beats naive by >= 3 % relative MAPE AND the
Diebold-Mariano test (APE loss) gives p < 0.05 in its favour.
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd
from sqlalchemy import Engine, text

from cropcast.config import settings
from cropcast.features.series import SERIES_KEY, Series, load_series
from cropcast.features.snapshot import load_snapshot, take_snapshot
from cropcast.models.dm import ape, dm_test
from cropcast.tracking import configure_mlflow, run_url

log = logging.getLogger(__name__)

HORIZON = 7
N_FOLDS = 52
MIN_REL_IMPROVEMENT = 3.0  # percent of naive MAPE
MAX_P_VALUE = 0.05
PARENT_NAME = "phase2.5-signal-hunt"
KEY = [*SERIES_KEY, "target_date"]


def results_dir() -> Path:
    d = settings.reports_dir / "phase2_5"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class HuntData:
    prices: pd.DataFrame
    weather: pd.DataFrame
    kerala_arrivals: pd.DataFrame  # commodity, date, total_tonnes (all Kerala markets)
    series: list[Series]
    last_date: date


def take(engine: Engine, asof: date) -> None:
    """One read from the DB: the modelled series + weather + Kerala arrival totals."""
    series = load_series()
    take_snapshot(engine, series, asof)
    with engine.connect() as conn:
        tot = pd.read_sql(
            text(
                "SELECT commodity, date, sum(arrivals_tonnes)::float8 AS total_tonnes, "
                "count(*) AS n_series FROM prices_clean WHERE date <= :d "
                "GROUP BY commodity, date"
            ),
            conn,
            params={"d": asof},
        )
    tot.to_parquet(settings.data_dir / "snapshots" / f"kerala_arrivals_{asof}.parquet", index=False)


def load(asof: date) -> HuntData:
    snap = load_snapshot(asof)
    tot = pd.read_parquet(settings.data_dir / "snapshots" / f"kerala_arrivals_{asof}.parquet")
    return HuntData(snap.prices, snap.weather, tot, load_series(), snap.last_date)


# --- scoring -----------------------------------------------------------------------------


def wins(rel_improvement: float, dm_stat: float, p_value: float) -> bool:
    return bool(rel_improvement >= MIN_REL_IMPROVEMENT and dm_stat < 0 and p_value < MAX_P_VALUE)


def score(
    preds: pd.DataFrame, model: str, reference: str = "naive", horizon: int = HORIZON
) -> pd.DataFrame:
    """Per crop + 'all': MAPE of `model` vs `reference` on identical rows, DM test, verdict."""
    m = preds[preds["model"] == model].set_index(KEY)
    r = preds[preds["model"] == reference].set_index(KEY)
    both = m[["actual", "pred"]].join(r[["pred"]], rsuffix="_ref", how="inner").reset_index()
    rows = []
    groups = [("all", both), *both.groupby("commodity", observed=True)]
    for crop, g in groups:
        loss_m, loss_r = ape(g["actual"], g["pred"]), ape(g["actual"], g["pred_ref"])
        mape_m, mape_r = float(loss_m.mean()), float(loss_r.mean())
        rel = (1 - mape_m / mape_r) * 100 if mape_r else float("nan")
        dm = dm_test(loss_m, loss_r, g["target_date"], horizon)
        rows.append(
            {
                "crop": str(crop),
                "n": len(g),
                f"mape_{model}": mape_m,
                f"mape_{reference}": mape_r,
                "rel_improvement_pct": rel,
                "dm_stat": dm.stat,
                "dm_p": dm.p_value,
                "wins": wins(rel, dm.stat, dm.p_value),
            }
        )
    return pd.DataFrame(rows)


# --- MLflow -----------------------------------------------------------------------------


def _parent_id() -> str:
    configure_mlflow()
    exp = mlflow.get_experiment_by_name("cropcast-backtest")
    assert exp is not None
    found = mlflow.search_runs(
        [exp.experiment_id],
        filter_string=f"tags.signal_hunt_parent = '1' and attributes.run_name = '{PARENT_NAME}'",
        output_format="list",
    )
    if found:
        return str(found[0].info.run_id)
    with mlflow.start_run(run_name=PARENT_NAME, tags={"signal_hunt_parent": "1"}) as run:
        mlflow.log_params(
            {
                "yardstick": f"{N_FOLDS}-fold walk-forward, h={HORIZON}, p50",
                "rule": f">= {MIN_REL_IMPROVEMENT}% rel. MAPE vs naive AND DM p < {MAX_P_VALUE}",
            }
        )
        return str(run.info.run_id)


def log_experiment(
    name: str,
    description: str,
    params: dict[str, Any],
    tables: dict[str, pd.DataFrame],
    headline: dict[str, float],
    verdict: str,
) -> str | None:
    """Child run under the signal-hunt parent + local JSON/CSV copies. Returns run URL."""
    out = results_dir()
    for tname, t in tables.items():
        t.to_csv(out / f"{name}_{tname}.csv", index=False)
    summary = {"name": name, "description": description, "params": params,
               "headline": headline, "verdict": verdict}  # fmt: skip
    (out / f"{name}.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    if settings.mlflow_tracking_uri is None:
        return None
    parent = _parent_id()
    with (
        mlflow.start_run(run_id=parent),
        mlflow.start_run(run_name=name, nested=True, tags={"verdict": verdict}) as run,
    ):
        mlflow.log_params({"description": description[:250], **params})
        mlflow.log_metrics({k: float(v) for k, v in headline.items() if pd.notna(v)})
        with tempfile.TemporaryDirectory() as tmp:
            for tname, t in tables.items():
                p = Path(tmp) / f"{name}_{tname}.csv"
                t.to_csv(p, index=False)
                mlflow.log_artifact(str(p))
        url = run_url(run)
    log.info("experiment logged", extra={"experiment": name, "verdict": verdict, "url": url})
    return url
