"""Live evaluation: matured forecasts and shadow predictions joined with actual prices.

* Price champion: rolling 28-day MAPE (p50) vs naive (the last price at forecast time) and
  p10-p90 interval coverage, per crop x horizon (+ 'all').
* Move challenger: exactly the tests in reports/preregistration_e4a.md -> per-crop verdict
  "insufficient data" | "fail" | "pass".
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score
from sqlalchemy import Engine, text

from cropcast.models.dm import dm_test
from cropcast.models.move import CLASSES, HORIZON, JUDGED_CROPS, THRESHOLD

log = logging.getLogger(__name__)

WINDOW_DAYS = 28
# Pre-registered constants (reports/preregistration_e4a.md).
ALPHA = 0.05
HAC_LAG = 6
MIN_WEEKS = 12
MIN_MOVES = 30
MIN_PRECISION = 0.55
MIN_LIFT_PP = 0.10


# --- price champion ----------------------------------------------------------------------


def matured_forecasts(engine: Engine, asof: date, window_days: int = WINDOW_DAYS) -> pd.DataFrame:
    sql = """
        SELECT f.commodity, f.market, f.variety, f.horizon, f.forecast_date, f.target_date,
               f.p10::float8 AS p10, f.p50::float8 AS p50, f.p90::float8 AS p90,
               f.last_value::float8 AS last_value, f.model_version,
               c.modal_price::float8 AS actual
        FROM forecasts f
        JOIN prices_clean c ON c.commodity = f.commodity AND c.market = f.market
                           AND c.variety = f.variety AND c.date = f.target_date
        WHERE f.target_date <= :asof AND f.target_date > :start
    """
    with engine.connect() as conn:
        return pd.read_sql(
            text(sql), conn, params={"asof": asof, "start": asof - timedelta(days=window_days)}
        )


def price_live_metrics(m: pd.DataFrame) -> pd.DataFrame:
    """Per crop x horizon (+ 'all'): MAPE p50, naive MAPE, coverage of [p10, p90], n."""
    if m.empty:
        return pd.DataFrame(columns=["commodity", "horizon", "metric", "value", "naive_value"])
    rows = []
    groups = [
        *m.groupby(["commodity", "horizon"]),
        *(((("all", h)), g) for h, g in m.groupby("horizon")),
    ]
    for (crop, h), g in groups:
        ape = (g["p50"] - g["actual"]).abs() / g["actual"] * 100
        ape_naive = (g["last_value"] - g["actual"]).abs() / g["actual"] * 100
        cover = ((g["p10"] <= g["actual"]) & (g["actual"] <= g["p90"])).mean() * 100
        base = {"commodity": crop, "horizon": int(h)}
        rows += [
            {**base, "metric": "mape_28d", "value": ape.mean(), "naive_value": ape_naive.mean()},
            {**base, "metric": "coverage_80_28d", "value": cover, "naive_value": None},
            {**base, "metric": "n_28d", "value": float(len(g)), "naive_value": None},
        ]
    return pd.DataFrame(rows)


# --- move challenger (pre-registered) --------------------------------------------------------


def matured_shadow(engine: Engine, asof: date, spec_hash: str) -> pd.DataFrame:
    sql = """
        SELECT s.*, s.last_value::float8 AS last_value_f, c.modal_price::float8 AS actual
        FROM shadow_predictions s
        JOIN prices_clean c ON c.commodity = s.commodity AND c.market = s.market
                           AND c.variety = s.variety AND c.date = s.target_date
        WHERE s.target_date <= :asof AND s.spec_hash = :spec
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params={"asof": asof, "spec": spec_hash})


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-adjusted p-values (missing / NaN p count as 1: conservative)."""
    items = sorted(
        ((k, 1.0 if not np.isfinite(v) else v) for k, v in pvalues.items()), key=lambda kv: kv[1]
    )
    m, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


def _balanced_loss(y: pd.Series, pred: pd.Series) -> pd.Series:
    share = y.value_counts(normalize=True)
    w = y.map(lambda c: 1.0 / (len(CLASSES) * share[c]))
    return (pred != y).astype(float) * w * 100


def shadow_evaluation(m: pd.DataFrame) -> pd.DataFrame:
    """One row per judged crop with every pre-registered statistic and the verdict."""
    rows: list[dict[str, Any]] = []
    m = m.copy()
    if len(m):
        chg = m["actual"] / m["last_value_f"] - 1
        m["y"] = np.select([chg > THRESHOLD, chg < -THRESHOLD], ["up", "down"], default="flat")
    for crop in JUDGED_CROPS:
        g = m[m["commodity"] == crop] if len(m) else m
        r: dict[str, Any] = {"crop": crop, "n": len(g)}
        if len(g):
            td = pd.to_datetime(g["target_date"])
            r["first_target"], r["last_target"] = str(td.min().date()), str(td.max().date())
            r["days_covered"] = int((td.max() - td.min()).days)
            r["n_moves"] = int((g["y"] != "flat").sum())
            r["macro_f1"] = float(
                f1_score(
                    g["y"], g["pred_class"], average="macro", labels=list(CLASSES), zero_division=0
                )
            )
            for cls in ("up", "down"):
                r[f"base_rate_{cls}"] = float((g["y"] == cls).mean())
                r[f"n_calls_{cls}"] = int((g["pred_class"] == cls).sum())
                r[f"precision_{cls}"] = float(
                    precision_score(
                        g["y"], g["pred_class"], labels=[cls], average="macro", zero_division=0
                    )
                )
            loss = _balanced_loss(g["y"], g["pred_class"])
            for base, col in (("flat", None), ("trend", "trend_class")):
                ref = pd.Series("flat", index=g.index) if col is None else g[col]
                dm = dm_test(loss, _balanced_loss(g["y"], ref), g["target_date"], HAC_LAG + 1)
                r[f"dm_stat_vs_{base}"], r[f"dm_p_vs_{base}"] = dm.stat, dm.p_value
        else:
            r.update({"days_covered": 0, "n_moves": 0})
        rows.append(r)
    out = pd.DataFrame(rows)
    for base in ("flat", "trend"):
        col = f"dm_p_vs_{base}"
        ps = dict(zip(out["crop"], out[col] if col in out else [np.nan] * len(out), strict=True))
        adj = holm(ps)
        out[f"holm_p_vs_{base}"] = out["crop"].map(adj)
    out["verdict"] = [_verdict(r) for r in out.to_dict("records")]
    return out


def _verdict(r: dict[Any, Any]) -> str:
    enough = r.get("days_covered", 0) >= MIN_WEEKS * 7 and r.get("n_moves", 0) >= MIN_MOVES
    if not enough:
        return "insufficient data"
    significant = all(
        r.get(f"holm_p_vs_{b}", 1.0) < ALPHA and r.get(f"dm_stat_vs_{b}", 0.0) < 0
        for b in ("flat", "trend")
    )
    practical = all(
        r.get(f"precision_{c}", 0.0) >= MIN_PRECISION
        and r.get(f"precision_{c}", 0.0) >= r.get(f"base_rate_{c}", 1.0) + MIN_LIFT_PP
        for c in ("up", "down")
    )
    return "pass" if significant and practical else "fail"


def shadow_metric_rows(ev: pd.DataFrame) -> pd.DataFrame:
    keep = [
        "n",
        "n_moves",
        "days_covered",
        "macro_f1",
        "precision_up",
        "precision_down",
        "base_rate_up",
        "base_rate_down",
        "dm_p_vs_flat",
        "dm_p_vs_trend",
        "holm_p_vs_flat",
        "holm_p_vs_trend",
    ]
    rows = []
    for r in ev.to_dict("records"):
        for k in keep:
            v = r.get(k)
            if v is not None and pd.notna(v):
                rows.append(
                    {
                        "commodity": r["crop"],
                        "horizon": HORIZON,
                        "metric": k,
                        "value": float(v),
                        "naive_value": None,
                    }
                )
    return pd.DataFrame(rows)
