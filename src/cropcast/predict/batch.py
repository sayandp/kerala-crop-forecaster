"""Daily batch predictions (no online inference).

* predict: `cropcast-price-h{h}@champion` for every modelled series x h in {1, 7, 14}
  -> forecasts (p10/p50/p90, model name + version, run_id).
* shadow: `cropcast-move-h7@challenger` for the pre-registered crops -> shadow_predictions.
  Refuses to run unless reports/preregistration_e4a.md is committed (records its commit).

Both are keyed by the DATA AS-OF date (the latest price date in the snapshot), not the run
date: GitHub starts the "evening" cron hours late, after midnight IST, so a run-date key labelled
yesterday's prices as today's (fixed 2026-10-09; shadow: preregistration Amendment 2).
Immutable: rows are INSERT ... ON CONFLICT DO NOTHING, and a run whose as-of date is not newer
than the last stored one writes nothing (no new price data -> no new predictions).
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import date
from typing import Any

import mlflow
import pandas as pd
from mlflow import MlflowClient
from sqlalchemy import Engine, text

from cropcast.config import PROJECT_ROOT
from cropcast.db import _records_any
from cropcast.features.build import build_features
from cropcast.features.series import Series
from cropcast.features.snapshot import Snapshot
from cropcast.models.move import CLASSES, HORIZON, JUDGED_CROPS, spec_hash, trend_class
from cropcast.models.training import HORIZONS
from cropcast.registry.promote import (
    MOVE_MODEL,
    NAIVE_ROUTED_TAG,
    alias_version,
    price_model_name,
)

log = logging.getLogger(__name__)

PREREG_PATH = "reports/preregistration_e4a.md"


def data_asof(snap: Snapshot, run_date: date) -> date:
    """Latest price date used (the snapshot is already cut at the run date)."""
    return min(snap.last_date, run_date)


def last_asof(engine: Engine, table: str) -> date | None:
    """Newest as-of date already predicted (forecasts / shadow_predictions)."""
    assert table in ("forecasts", "shadow_predictions")
    with engine.connect() as conn:
        value = conn.execute(text(f"SELECT max(forecast_date) FROM {table}")).scalar()
    return value if isinstance(value, date) else None


def _skip(engine: Engine, table: str, asof: date) -> date | None:
    """The stored as-of date if `asof` is not newer (nothing new to predict), else None."""
    last = last_asof(engine, table)
    if last is not None and asof <= last:
        log.info(
            "no new price data: skipping",
            extra={"table": table, "as_of": str(asof), "last": str(last)},
        )
        return last
    return None


def route_naive(rows: pd.DataFrame, pred: pd.DataFrame, crops: set[str]) -> pd.Series:
    """Per-crop guard: rows of `crops` get the naive point (last price) and the same band.

    The band does not depend on the point forecast (both champions share the LGBM quantile
    band around log1p(last price)); only the clamp keeps p50 inside it. Returns the mask."""
    from cropcast.bot.names import crop_of

    mask = pd.Series(
        [
            crop_of(str(c), str(m), str(v)) in crops
            for c, m, v in zip(rows["commodity"], rows["market"], rows["variety"], strict=True)
        ],
        index=rows.index,
    )
    if mask.any():
        last = rows.loc[mask, "last_value"].astype(float)
        pred.loc[mask, "p50"] = last
        pred.loc[mask, "p10"] = pred.loc[mask, "p10"].clip(upper=last)
        pred.loc[mask, "p90"] = pred.loc[mask, "p90"].clip(lower=last)
    return mask


def origin_rows(snap: Snapshot, series: list[Series], run_date: date, horizon: int) -> pd.DataFrame:
    """Feature rows whose origin is the run date (one per live series)."""
    f = build_features(snap.prices, snap.weather, run_date, horizon, series)
    return f[pd.to_datetime(f["origin_date"]) == pd.Timestamp(run_date)].reset_index(drop=True)


def _load(name: str, alias: str) -> tuple[Any, str]:
    version = alias_version(MlflowClient(), name, alias)
    if version is None:
        raise RuntimeError(f"no {name}@{alias} in the registry; run the weekly retrain first")
    return mlflow.pyfunc.load_model(f"models:/{name}@{alias}"), version


def predict_prices(
    engine: Engine,
    snap: Snapshot,
    series: list[Series],
    run_date: date,
    run_id: int | None,
    dry_run: bool = False,
) -> pd.DataFrame:
    asof = data_asof(snap, run_date)
    if (last := _skip(engine, "forecasts", asof)) is not None:
        empty = pd.DataFrame()
        empty.attrs.update(as_of=asof, skipped=f"no new price data since as-of {last}")
        return empty
    frames = []
    for h in HORIZONS:
        name = price_model_name(h)
        model, version = _load(name, "champion")
        rows = origin_rows(snap, series, asof, h)
        pred = model.predict(rows).copy()
        tags = MlflowClient().get_model_version(name, version).tags or {}
        routed = set(json.loads(tags.get(NAIVE_ROUTED_TAG, "[]")))
        naive_rows = route_naive(rows, pred, routed)
        frames.append(
            rows[["commodity", "market", "variety", "origin_date", "target_date", "last_value"]]
            .astype({"commodity": str, "market": str, "variety": str})
            .assign(
                horizon=h,
                p10=pred["p10"].round(2),
                p50=pred["p50"].round(2),
                p90=pred["p90"].round(2),
                model_name=name,
                model_version=[f"{version}:naive" if n else version for n in naive_rows],
                run_id=run_id,
            )
            .rename(columns={"origin_date": "forecast_date"})
        )
    out = pd.concat(frames, ignore_index=True)
    if not dry_run:
        cols = (
            "run_id",
            "forecast_date",
            "target_date",
            "horizon",
            "commodity",
            "market",
            "variety",
            "p10",
            "p50",
            "p90",
            "last_value",
            "model_name",
            "model_version",
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO forecasts ({', '.join(cols)}) VALUES "
                    f"({', '.join(':' + c for c in cols)}) "
                    "ON CONFLICT (forecast_date, horizon, commodity, market, variety) DO NOTHING"
                ),
                _records_any(out, cols),
            )
    out.attrs.update(as_of=asof, skipped=None)
    return out


def prereg_commit() -> str:
    """Commit SHA that added the pre-registration (empty if not committed)."""
    try:
        res = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%H", "--", PREREG_PATH],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = res.stdout.strip().splitlines()
    return lines[-1] if lines else ""


def predict_shadow(
    engine: Engine,
    snap: Snapshot,
    series: list[Series],
    run_date: date,
    run_id: int | None,
    dry_run: bool = False,
) -> pd.DataFrame:
    commit = prereg_commit()
    if not commit:
        raise RuntimeError(
            f"{PREREG_PATH} is not committed (or git history is shallow): shadow predictions "
            "may only be made after the pre-registration commit"
        )
    model, version = _load(MOVE_MODEL, "challenger")
    tags = MlflowClient().get_model_version(MOVE_MODEL, version).tags
    current = spec_hash(series)
    if tags.get("spec_hash") != current:
        raise RuntimeError(
            f"{MOVE_MODEL} v{version} spec {tags.get('spec_hash')} != code spec {current}: "
            "retrain before making shadow predictions"
        )
    asof = data_asof(snap, run_date)
    if (last := _skip(engine, "shadow_predictions", asof)) is not None:
        empty = pd.DataFrame(columns=["pred_class"])
        empty.attrs.update(as_of=asof, skipped=f"no new price data since as-of {last}")
        return empty
    rows = origin_rows(snap, series, asof, HORIZON)
    rows = rows[rows["commodity"].astype(str).isin(JUDGED_CROPS)].reset_index(drop=True)
    pred = model.predict(rows)
    out = (
        rows[["commodity", "market", "variety", "origin_date", "target_date", "last_value"]]
        .astype({"commodity": str, "market": str, "variety": str})
        .rename(columns={"origin_date": "forecast_date"})
    )
    out = out.assign(
        pred_class=pred["pred_class"].to_numpy(),
        p_down=pred["p_down"].to_numpy(),
        p_flat=pred["p_flat"].to_numpy(),
        p_up=pred["p_up"].to_numpy(),
        trend_class=[CLASSES[i] for i in trend_class(rows)],
        model_version=version,
        spec_hash=current,
        prereg_commit=commit,
        run_id=run_id,
    )
    if not dry_run:
        cols = (
            "forecast_date",
            "target_date",
            "commodity",
            "market",
            "variety",
            "pred_class",
            "p_down",
            "p_flat",
            "p_up",
            "trend_class",
            "last_value",
            "model_version",
            "spec_hash",
            "prereg_commit",
            "run_id",
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO shadow_predictions ({', '.join(cols)}) VALUES "
                    f"({', '.join(':' + c for c in cols)}) "
                    "ON CONFLICT (forecast_date, commodity, market, variety) DO NOTHING"
                ),
                _records_any(out, cols),
            )
    out.attrs.update(as_of=asof, skipped=None)
    return out
