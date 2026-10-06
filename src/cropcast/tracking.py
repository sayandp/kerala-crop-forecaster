"""MLflow setup (DagsHub when MLFLOW_TRACKING_URI is set, else local) and run helpers.

Credentials come from settings (never read os.environ elsewhere); MLflow itself reads them
from the process environment, so they are exported here once.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import mlflow

from cropcast.config import PROJECT_ROOT, settings

log = logging.getLogger(__name__)

EXPERIMENT = "cropcast-backtest"


def configure_mlflow() -> str:
    """Point MLflow at DagsHub (or local ./mlruns) and select the experiment. Returns URI."""
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    if settings.mlflow_tracking_uri:
        uri = settings.mlflow_tracking_uri
        if settings.mlflow_tracking_username:
            os.environ["MLFLOW_TRACKING_USERNAME"] = settings.mlflow_tracking_username
        if settings.mlflow_tracking_password is not None:
            os.environ["MLFLOW_TRACKING_PASSWORD"] = (
                settings.mlflow_tracking_password.get_secret_value()
            )
    else:
        # Local fallback: MLflow 3 put the plain ./mlruns file store in maintenance mode,
        # so run metadata goes to SQLite (mlflow.db) and artifacts to ./mlruns.
        uri = f"sqlite:///{(PROJECT_ROOT / 'mlflow.db').as_posix()}"
    mlflow.set_tracking_uri(uri)
    if mlflow.get_experiment_by_name(EXPERIMENT) is None and not uri.startswith("http"):
        mlflow.create_experiment(EXPERIMENT, artifact_location=(PROJECT_ROOT / "mlruns").as_uri())
    mlflow.set_experiment(EXPERIMENT)
    log.info("mlflow configured", extra={"tracking_uri": uri, "experiment": EXPERIMENT})
    return uri


def run_url(run: Any) -> str | None:
    """Web URL of a run on DagsHub/MLflow UI (None for a local file store)."""
    uri = mlflow.get_tracking_uri()
    if not uri.startswith("http"):
        return None
    return f"{uri.rstrip('/')}/#/experiments/{run.info.experiment_id}/runs/{run.info.run_id}"


def delete_experiment(name: str) -> bool:
    """Soft-delete an experiment by name (e.g. the DagsHub 'smoke-test'). True if deleted."""
    exp = mlflow.get_experiment_by_name(name)
    if exp is None or exp.lifecycle_stage == "deleted":
        return False
    mlflow.delete_experiment(exp.experiment_id)
    return True
