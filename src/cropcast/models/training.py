"""Phase 2 model steps: features -> train -> backtest, with MLflow logging.

Thin pipeline wrappers live in cropcast.pipeline (run_features / run_train / run_backtest).
One MLflow parent run per pipeline invocation, one nested child run per horizon.
Nothing is registered (promotion is Phase 3).
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import pandas as pd
from sqlalchemy import Engine

from cropcast.config import settings
from cropcast.features.build import (
    FEATURE_COLUMNS,
    FESTIVALS_PATH,
    TARGET,
    build_features,
)
from cropcast.features.series import SERIES_PATH, Series
from cropcast.features.snapshot import Snapshot, take_snapshot
from cropcast.models.backtest import (
    BacktestResult,
    comparison_table,
    make_folds,
    metrics_table,
    run_backtest,
)
from cropcast.models.lgbm import DEFAULT_PARAMS, QUANTILES, SEED, LGBMForecaster
from cropcast.tracking import configure_mlflow, run_url

log = logging.getLogger(__name__)

HORIZONS = (1, 7, 14)
N_FOLDS = 5
TEST_DAYS = 14
METRICS = ("mape", "smape", "mase", "coverage_80")


# --- features -----------------------------------------------------------------------


def features_dir() -> Path:
    return settings.data_dir / "features"


def prepare_features(
    engine: Engine, series: list[Series], asof: date
) -> tuple[Snapshot, dict[int, pd.DataFrame]]:
    """One DB read (snapshot) -> features per horizon, written to data/features/*.parquet."""
    snap = take_snapshot(engine, series, asof)
    last = snap.last_date
    out = features_dir()
    out.mkdir(parents=True, exist_ok=True)
    feats: dict[int, pd.DataFrame] = {}
    for h in HORIZONS:
        f = build_features(snap.prices, snap.weather, last, h, series)
        f.to_parquet(out / f"features_h{h}_{last}.parquet", index=False)
        feats[h] = f
    return snap, feats


# --- MLflow session -----------------------------------------------------------------


@dataclass
class MlflowSession:
    """Parent run for the invocation + one nested child run per horizon (resumable)."""

    parent_id: str | None = None
    children: dict[int, str] = field(default_factory=dict)
    url: str | None = None

    def start(self, run_name: str, params: dict[str, Any], tags: dict[str, str]) -> None:
        configure_mlflow()
        run = mlflow.start_run(run_name=run_name, tags=tags)
        self.parent_id = run.info.run_id
        self.url = run_url(run)
        mlflow.log_params(params)
        for path in (SERIES_PATH, FESTIVALS_PATH):
            mlflow.log_artifact(str(path), artifact_path="config")
        mlflow.log_dict({"features": FEATURE_COLUMNS}, "config/feature_list.json")
        log.info("mlflow parent run started", extra={"run_id": self.parent_id, "url": self.url})

    def child(self, horizon: int) -> Any:
        """Context manager for the horizon's nested run (created on first use)."""
        if horizon in self.children:
            return mlflow.start_run(run_id=self.children[horizon], nested=True)
        run = mlflow.start_run(run_name=f"h{horizon}", nested=True, tags={"horizon": str(horizon)})
        self.children[horizon] = run.info.run_id
        return run

    def end(self, status: str) -> None:
        while mlflow.active_run() is not None:
            mlflow.end_run(status=status)


def base_params(
    snap: Snapshot, series: list[Series], params: dict[str, Any], tuned: bool
) -> dict[str, Any]:
    return {
        "data_first_date": str(snap.first_date),
        "data_last_date": str(snap.last_date),
        "n_series": len(series),
        "n_price_rows": len(snap.prices),
        "horizons": ",".join(map(str, HORIZONS)),
        "n_folds": N_FOLDS,
        "test_days": TEST_DAYS,
        "seed": SEED,
        "quantiles": ",".join(map(str, QUANTILES)),
        "target": "log1p(modal_price); model learns change vs log1p(last value)",
        "portal_switch_date": str(settings.portal_switch_date),
        "tuned": tuned,
        **{f"lgbm_{k}": v for k, v in params.items()},
    }


# --- train ---------------------------------------------------------------------------


def _importance_plot(imp: pd.Series, horizon: int, path: Path) -> None:
    top = imp.head(20)[::-1]
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.barh(top.index, top.to_numpy(), color="#2a78d6", height=0.7)
    ax.set_title(f"LightGBM p50 feature importance (gain), h={horizon}", loc="left", fontsize=10)
    ax.set_xlabel("total gain")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", color="#e6e5e0", linewidth=0.6)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def train_final(
    features: dict[int, pd.DataFrame],
    params: dict[str, Any],
    session: MlflowSession | None,
) -> dict[int, LGBMForecaster]:
    """Fit the final per-horizon models on all rows with a known target; log artifacts."""
    models: dict[int, LGBMForecaster] = {}
    for h, f in sorted(features.items()):
        train = f.dropna(subset=[TARGET])
        model = LGBMForecaster(h, params=dict(params)).fit(train)
        models[h] = model
        if session is None:
            continue
        with session.child(h):
            mlflow.log_params(
                {
                    "horizon": h,
                    "train_rows": len(train),
                    "train_target_from": str(pd.to_datetime(train["target_date"]).min().date()),
                    "train_target_to": str(pd.to_datetime(train["target_date"]).max().date()),
                    **{f"best_iter_{q}": n for q, n in model.best_iterations.items()},
                }
            )
            with tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                for p in model.save(d / "models"):
                    mlflow.log_artifact(str(p), artifact_path="models")
                imp = model.feature_importance()
                imp.rename("gain").to_csv(d / "feature_importance.csv")
                _importance_plot(imp, h, d / "feature_importance.png")
                mlflow.log_artifact(str(d / "feature_importance.csv"))
                mlflow.log_artifact(str(d / "feature_importance.png"))
    return models


# --- backtest ------------------------------------------------------------------------


def _metric_key(name: str) -> str:
    return name.replace(" ", "_").replace("·", "").replace("/", "_")


def backtest_and_log(
    features: dict[int, pd.DataFrame],
    snap: Snapshot,
    params: dict[str, Any],
    session: MlflowSession | None,
) -> tuple[BacktestResult, dict[str, pd.DataFrame]]:
    result = run_backtest(
        features,
        snap.prices,
        snap.last_date,
        lgbm_params=params,
        n_folds=N_FOLDS,
        test_days=TEST_DAYS,
    )
    preds = result.predictions
    tables = {
        "by_series_horizon": comparison_table(preds, ["commodity", "market", "variety", "horizon"]),
        "by_commodity_horizon": comparison_table(preds, ["commodity", "horizon"]),
        "by_horizon": comparison_table(preds, ["horizon"]),
        "by_fold_horizon": comparison_table(preds, ["horizon", "fold"]),
    }
    if session is None:
        return result, tables

    switch = pd.Timestamp(settings.portal_switch_date)
    post_switch = {
        h: sum(f.cutoff >= switch for f in make_folds(snap.last_date, h, N_FOLDS, TEST_DAYS))
        for h in features
    }
    for h in sorted(features):
        hp = preds[preds["horizon"] == h]
        with session.child(h):
            for row in comparison_table(hp, ["fold"]).to_dict("records"):
                mlflow.log_metrics(
                    {
                        "fold_mape_lgbm": float(row["mape_lgbm"]),
                        "fold_mape_naive": float(row["mape_naive"]),
                        "fold_mape_seasonal_naive": float(row["mape_seasonal_naive"]),
                        "fold_coverage_80": float(row["coverage_80_lgbm"]),
                    },
                    step=int(row["fold"]),
                )
            agg = metrics_table(hp, [])
            for r in agg.itertuples(index=False):
                mlflow.log_metrics(
                    {
                        f"{m}_{r.model}": float(getattr(r, m))
                        for m in METRICS
                        if pd.notna(getattr(r, m))
                    }
                )
            mlflow.log_metric("folds_after_portal_switch", post_switch[h])
            for r in metrics_table(hp, ["commodity"]).itertuples(index=False):
                for m in ("mape", "mase"):
                    mlflow.log_metric(f"{m}_{r.model}_{r.commodity}", float(getattr(r, m)))
    # Parent: per-horizon headline numbers, always with naive next to LGBM.
    for hr in tables["by_horizon"].to_dict("records"):
        h = int(hr["horizon"])
        keys = ("mape_lgbm", "mape_naive", "mape_seasonal_naive", "mase_lgbm", "mase_naive",
                "coverage_80_lgbm")  # fmt: skip
        mlflow.log_metrics({f"h{h}_{k}": float(hr[k]) for k in keys})
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        preds.to_csv(d / "backtest_predictions.csv", index=False)
        mlflow.log_artifact(str(d / "backtest_predictions.csv"), artifact_path="backtest")
        for name, t in tables.items():
            t.to_csv(d / f"{name}.csv", index=False)
            mlflow.log_artifact(str(d / f"{name}.csv"), artifact_path="backtest")
        folds = [
            {
                "horizon": f.horizon,
                "fold": f.number,
                "cutoff": str(f.cutoff.date()),
                "test_origins_to": str(f.test_end.date()),
                "targets_from": str(f.target_start.date()),
                "targets_to": str(f.target_end.date()),
                "after_portal_switch": bool(f.cutoff >= switch),
            }
            for f in result.folds
        ]
        (d / "folds.json").write_text(json.dumps(folds, indent=1), encoding="utf-8")
        mlflow.log_artifact(str(d / "folds.json"), artifact_path="backtest")
    return result, tables


def model_metrics_rows(predictions: pd.DataFrame, model_version: str | None) -> pd.DataFrame:
    """Aggregate backtest rows for model_metrics: commodity ('all' too) x horizon x model."""
    per = metrics_table(predictions, ["commodity", "horizon"])
    overall = metrics_table(predictions, ["horizon"]).assign(commodity="all")
    long = pd.concat([per, overall], ignore_index=True)
    long["model"] = long["model"].astype(str)
    rows = long.melt(
        id_vars=["commodity", "horizon", "model"], value_vars=list(METRICS), var_name="metric"
    ).dropna(subset=["value"])
    naive = rows[rows["model"] == "naive"][["commodity", "horizon", "metric", "value"]]
    rows = rows.merge(
        naive.rename(columns={"value": "naive_value"}),
        on=["commodity", "horizon", "metric"],
        how="left",
    )
    rows["model_name"] = rows.pop("model")
    rows["model_version"] = model_version
    return rows[
        ["model_name", "model_version", "commodity", "horizon", "metric", "value", "naive_value"]
    ]


def default_params() -> dict[str, Any]:
    return dict(DEFAULT_PARAMS)
