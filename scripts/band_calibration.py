"""Evaluate per-crop split-conformal calibration of the p10-p90 band on a long walk-forward.

    uv run python scripts/band_calibration.py --folds 31            # evaluate (+ MLflow run)
    uv run python scripts/band_calibration.py --folds 31 --store    # + model_metrics rows

Raw vs calibrated coverage per crop x horizon on the last (folds - 5) folds (the first 5 only
seed the rolling calibration window). Writes reports/band_calibration_<date>/.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import mlflow
import pandas as pd

from cropcast import db
from cropcast.bot.names import crop_of
from cropcast.config import settings
from cropcast.features.series import load_series
from cropcast.models import calibration as cal
from cropcast.models.backtest import run_backtest
from cropcast.models.training import prepare_features
from cropcast.tracking import configure_mlflow

HORIZONS = (1, 7, 14)


def table(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    g = df.groupby(by)
    return pd.DataFrame(
        {
            "n": g.size(),
            "raw_%": g.apply(lambda x: cal.coverage(x, "lo", "hi"), include_groups=False).round(1),
            "calibrated_%": g.apply(
                lambda x: cal.coverage(x, "lo_cal", "hi_cal"), include_groups=False
            ).round(1),
            "median_q": g["q"].median().round(4),
        }
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--folds", type=int, default=31)
    p.add_argument("--store", action="store_true", help="write per-crop coverage to model_metrics")
    p.add_argument(
        "--from-predictions",
        type=Path,
        help="reuse a saved predictions.parquet (skip the walk-forward)",
    )
    args = p.parse_args(argv)
    engine = db.get_engine()
    if args.from_predictions:
        bt = pd.read_parquet(args.from_predictions)
        last = pd.to_datetime(bt["target_date"]).max().date()
        out_dir = args.from_predictions.parent
    else:
        snap, feats = prepare_features(engine, load_series(), date.today())
        bt = run_backtest(
            {h: feats[h] for h in HORIZONS},
            snap.prices,
            snap.last_date,
            n_folds=args.folds,
            quantiles=(0.1, 0.5, 0.9),
        ).predictions
        last = snap.last_date
        out_dir = settings.reports_dir / f"band_calibration_{last}"
        out_dir.mkdir(parents=True, exist_ok=True)
        bt.to_parquet(out_dir / "predictions.parquet", index=False)

    band = cal.served_band(bt, crop_of)
    res = cal.rolling_calibrate(band)
    by_crop_h = table(res, ["crop", "horizon"])
    by_h = table(res, ["horizon"])
    pooled = {
        "raw_%": round(cal.coverage(res, "lo", "hi"), 1),
        "calibrated_%": round(cal.coverage(res, "lo_cal", "hi_cal"), 1),
        "n": len(res),
    }
    by_crop_h.to_csv(out_dir / "coverage_by_crop_horizon.csv")
    by_h.to_csv(out_dir / "coverage_by_horizon.csv")
    by_crop = table(res, ["crop"])
    by_crop.to_csv(out_dir / "coverage_by_crop.csv")
    # Ship rule (2026-10-09): pooled ~80 % and every crop (pooled over horizons) within 70-90 %.
    outside = by_crop[(by_crop["calibrated_%"] < 70) | (by_crop["calibrated_%"] > 90)]
    cells_outside = by_crop_h[(by_crop_h["calibrated_%"] < 70) | (by_crop_h["calibrated_%"] > 90)]
    ship = abs(pooled["calibrated_%"] - 80) <= 2.5 and outside.empty
    lines = [
        f"# Band calibration ({last}, {args.folds} folds, {len(res)} evaluated forecasts)",
        "",
        f"Pooled coverage raw {pooled['raw_%']} % -> calibrated "
        f"{pooled['calibrated_%']} % (target 80 %).",
        f"Crops outside 70-90 % after calibration: {len(outside)}; crop x horizon cells: "
        f"{len(cells_outside)} ({', '.join(f'{c} h={h}' for c, h in cells_outside.index)}). "
        f"Ship: {ship}.",
        "",
        "## By crop (pooled over horizons)",
        "",
        by_crop.to_markdown(),
        "",
        "## By horizon",
        "",
        by_h.to_markdown(),
        "",
        "## By crop x horizon",
        "",
        by_crop_h.to_markdown(),
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    configure_mlflow()
    mlflow.set_experiment("cropcast-backtest")
    with mlflow.start_run(run_name=f"band-calibration-{last}"):
        mlflow.log_params(
            {
                "method": "split-conformal CQR, log1p, per crop x horizon",
                "window_days": cal.WINDOW_DAYS,
                "min_scores": cal.MIN_SCORES,
                "target": cal.TARGET_COVERAGE,
                "folds": args.folds,
            }
        )
        mlflow.log_metrics(
            {
                "coverage_raw": pooled["raw_%"],
                "coverage_calibrated": pooled["calibrated_%"],
                "crops_outside_70_90": float(len(outside)),
                "cells_outside_70_90": float(len(cells_outside)),
                "ship": float(ship),
            }
        )
        mlflow.log_artifacts(str(out_dir))

    if args.store:
        rows = []
        for (crop, h), r in by_crop_h.iterrows():
            for model, col in (("band_raw", "raw_%"), ("band_conformal", "calibrated_%")):
                rows.append(
                    {
                        "model_name": model,
                        "model_version": None,
                        "commodity": crop,
                        "horizon": int(h),
                        "metric": "coverage_80",
                        "value": float(r[col]),
                        "naive_value": None,
                    }
                )
        db.insert_model_metrics(pd.DataFrame(rows), None, "backtest", engine)
    return 0 if ship else 2


if __name__ == "__main__":
    sys.exit(main())
