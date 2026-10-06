"""Builds notebooks/02_backtest_report.ipynb (kept as code so the notebook diff is reviewable).

    uv run python notebooks/build_backtest_report.py
    uv run jupyter nbconvert --to notebook --execute --inplace notebooks/02_backtest_report.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

HERE = Path(__file__).resolve().parent
cells: list[nbf.NotebookNode] = []


def md(src: str) -> None:
    cells.append(nbf.v4.new_markdown_cell(src.strip()))


def code(src: str) -> None:
    cells.append(nbf.v4.new_code_cell(src.strip()))


md("""
# Phase 2 — backtest report

LightGBM (global, quantile, direct per horizon) vs naive / seasonal-naive / 7-day MA on the 19
series in `config/series.yaml`. Reads the latest `reports/backtest_<date>/` written by
`python -m cropcast.pipeline --steps features,train,backtest` and the matching parquet snapshot.

Official backtest: 5 walk-forward folds × 14-day windows ending at the latest date (all after the
Agmarknet 2.0 portal switch). Sections 5–6 add a **diagnostic** 52-fold (≈ 2-year) h=7 backtest,
p50 only, to look at seasonality and the portal switch — it is not the reported metric.
""")

code("""
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from cropcast.config import settings
from cropcast.features.build import build_features
from cropcast.features.series import load_series
from cropcast.models.backtest import comparison_table, metrics_table, run_backtest

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200, "display.max_columns", 30, "display.max_rows", 80)

# Fixed categorical order: one hue per model (validated palette), never re-ordered.
MODEL_COLORS = {"lgbm": "#2a78d6", "naive": "#eb6834", "seasonal_naive": "#1baf7a",
                "moving_average": "#eda100"}
INK, MUTED, GRID = "#0b0b0b", "#898781", "#e6e5e0"
plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "axes.axisbelow": True, "lines.linewidth": 1.2,
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold", "legend.frameon": False,
})

report = sorted((settings.reports_dir).glob("backtest_*"))[-1]
last = pd.Timestamp(report.name.removeprefix("backtest_"))
preds = pd.read_parquet(report / "predictions.parquet")
snap_path = sorted((settings.data_dir / "snapshots").glob("prices_clean_*.parquet"))[-1]
prices = pd.read_parquet(snap_path)
weather = pd.read_parquet(str(snap_path).replace("prices_clean_", "weather_"))
print(f"report: {report.name} | data to {last.date()} | {len(preds):,} prediction rows | "
      f"snapshot {snap_path.name}")
""")

md("## 1. Headline: LGBM vs baselines by horizon (all 19 series pooled)")
code("""
by_h = comparison_table(preds, ["horizon"])
by_h.round(3)
""")

md("## 2. Per crop × horizon")
code("""
by_c = comparison_table(preds, ["commodity", "horizon"])
display(by_c[["commodity", "horizon", "n_lgbm", "mape_lgbm", "mape_naive", "mape_seasonal_naive",
              "mape_moving_average", "mase_lgbm", "mase_naive", "coverage_80_lgbm",
              "lgbm_beats_naive"]].round(2))

long = metrics_table(preds, ["commodity", "horizon"])
crops = sorted(long["commodity"].unique())
models = list(MODEL_COLORS)
fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), sharey=False)
for ax, h in zip(axes, (1, 7, 14)):
    sub = long[long["horizon"] == h]
    x = np.arange(len(crops))
    w = 0.2
    for i, m in enumerate(models):
        vals = [sub[(sub.commodity == c) & (sub.model == m)]["mape"].squeeze() for c in crops]
        ax.bar(x + (i - 1.5) * w, vals, width=w * 0.9, color=MODEL_COLORS[m], label=m)
    ax.set_xticks(x, crops)
    ax.set_title(f"MAPE % by crop, h={h}", loc="left")
axes[0].set_ylabel("MAPE %")
axes[0].legend(fontsize=8)
fig.tight_layout()
""")

md("### Series where LGBM does not beat naive (MAPE)")
code("""
by_s = comparison_table(preds, ["commodity", "market", "variety", "horizon"])
losers = by_s[~by_s["lgbm_beats_naive"]]
print(f"{len(losers)} of {len(by_s)} series×horizon cells: LGBM MAPE >= naive MAPE")
losers[["commodity", "market", "variety", "horizon", "mape_lgbm", "mape_naive", "mase_lgbm",
        "mase_naive"]].round(2)
""")

md("## 3. Forecast vs actual with the p10–p90 band (h=7, one series per crop)")
code("""
pick = {"banana": ("Kayamkulam", "Nendran"), "coconut": ("Koduvayoor", "Big"),
        "pepper": ("Kannur", "Other"), "rubber": ("Pulpally", "Other"),
        "tapioca": ("Perumbavoor", "Tapioca")}
fig, axes = plt.subplots(5, 1, figsize=(11, 13))
for ax, (crop, (market, variety)) in zip(axes, pick.items()):
    s = preds[(preds.commodity == crop) & (preds.market == market) & (preds.variety == variety)
              & (preds.horizon == 7)].copy()
    s["target_date"] = pd.to_datetime(s["target_date"])
    lg = s[s.model == "lgbm"].sort_values("target_date")
    nv = s[s.model == "naive"].sort_values("target_date")
    ax.fill_between(lg.target_date, lg.p10, lg.p90, color=MODEL_COLORS["lgbm"], alpha=0.18,
                    linewidth=0, label="LGBM p10–p90")
    ax.plot(lg.target_date, lg.pred, color=MODEL_COLORS["lgbm"], label="LGBM p50")
    ax.plot(nv.target_date, nv.pred, color=MODEL_COLORS["naive"], ls="--", lw=1, label="naive")
    ax.plot(lg.target_date, lg.actual, "o", color=INK, ms=2.5, label="actual")
    ax.set_title(f"{crop} · {market} · {variety} — h=7 (Rs./quintal)", loc="left")
axes[0].legend(fontsize=8, ncol=4, loc="upper left")
fig.tight_layout()
""")

md("## 4. Feature importance (gain, latest fold's p50 model)")
code("""
fi = pd.read_csv(report / "feature_importance.csv").set_index("feature")
share = (fi / fi.sum() * 100).round(1)
display(share.sort_values("gain_h7", ascending=False).head(15))
top = share["gain_h7"].sort_values().tail(15)
fig, ax = plt.subplots(figsize=(7, 5))
ax.barh(top.index, top.to_numpy(), color=MODEL_COLORS["lgbm"], height=0.7)
ax.set_title("Share of total gain, h=7 (%)", loc="left")
fig.tight_layout()
""")

md("""
## 5. Diagnostic: error by month over ~2 years (h=7, p50 only)

52 walk-forward folds × 14 days. Does the Onam season (Aug–Sep) break the model?
""")
code("""
series = load_series()
f7 = build_features(prices, weather, last.date(), 7, series)
diag = run_backtest({7: f7}, prices, last.date(), n_folds=52, quantiles=(0.5,)).predictions
diag["month"] = pd.to_datetime(diag["target_date"]).dt.to_period("M").astype(str)
by_m = metrics_table(diag, ["month"])
piv = by_m.pivot(index="month", columns="model", values="mape")[["lgbm", "naive"]]
fig, ax = plt.subplots(figsize=(12, 3.8))
for m in ("lgbm", "naive"):
    ax.plot(piv.index, piv[m], marker="o", ms=3, color=MODEL_COLORS[m], label=m)
for i, mth in enumerate(piv.index):
    if mth[-2:] in ("08", "09"):
        ax.axvspan(i - 0.5, i + 0.5, color=GRID, zorder=0)
ax.set_title("Monthly MAPE %, h=7 (shaded: Aug–Sep, Onam season)", loc="left")
ax.tick_params(axis="x", rotation=60)
ax.legend()
fig.tight_layout()
diag_c = comparison_table(diag, ["commodity"])
diag_all = comparison_table(diag, ["horizon"])
display(diag_all[["n_lgbm", "mape_lgbm", "mape_naive", "mase_lgbm", "mase_naive"]].round(3))
diag_c[["commodity", "n_lgbm", "mape_lgbm", "mape_naive"]].round(2)
""")

code("""
diag["onam_season"] = pd.to_datetime(diag["target_date"]).dt.month.isin([8, 9])
comparison_table(diag, ["commodity", "onam_season"])[
    ["commodity", "onam_season", "n_lgbm", "mape_lgbm", "mape_naive"]].round(2)
""")

md("## 6. Diagnostic: before vs after the Agmarknet 2.0 portal switch")
code("""
switch = pd.Timestamp(settings.portal_switch_date)
diag["period"] = np.where(pd.to_datetime(diag["origin_date"]) >= switch, "post-switch", "pre-switch")
comparison_table(diag, ["period"])[["period", "n_lgbm", "mape_lgbm", "mape_naive", "mase_lgbm",
                                    "mase_naive"]].round(3)
""")

code("""
comparison_table(diag, ["commodity", "period"])[
    ["commodity", "period", "n_lgbm", "mape_lgbm", "mape_naive"]].round(2)
""")

md("""
## 7. Conclusions

*Numbers from the 2026-10-07 run on Neon data (prices to 2026-10-06), DagsHub parent run `08290bba`.*

**Headline — LightGBM does not beat the naive forecast.** Pooled over 19 series:

| h | LGBM MAPE | naive | seasonal-naive | 7-d MA | LGBM MASE | naive MASE | p10–p90 coverage |
|---|---|---|---|---|---|---|---|
| 1 | 2.59 | 2.58 | 4.67 | 3.21 | 1.15 | 1.16 | 82.7 % |
| 7 | 4.77 | 4.71 | 4.71 | 5.16 | 2.18 | 2.15 | 80.1 % |
| 14 | 7.08 | 6.97 | 6.97 | 7.38 | 3.42 | 3.21 | 76.8 % |

* The p50 forecast tracks the last price (section 3); the p50 models early-stop at ~50 trees —
  the learnable signal beyond "no change" is tiny. The ≈2-year diagnostic confirms it is not a
  window artefact: 5.28 vs 5.28 % at h=7 over 11k forecasts, in every quarter and pre/post switch.
* **Where LGBM wins:** rubber · Pulpally (all horizons, e.g. h=7 2.95 vs 3.24), tapioca ·
  Perumbavoor (12.2 vs 12.4), banana Elamad / Chenkal at h=14. **Where it loses most:**
  flat series (pepper and tapioca at North Paravur: naive MAPE 0.00 — any predicted move is
  error) and coconut at h=14 (6.1 vs 5.3).
* **Onam season breaks banana** (diagnostic): Aug–Sep MAPE 8.18 vs naive 7.91 — the festival
  flags are on the target date but 2–8 years of history give too few Onam cycles per series.
* **Portal switch:** errors are *lower* after 2025-11-07 for both models (h=7 ≈ 4.98 vs 5.52 %),
  i.e. the clean layer handles the cut-over; it is not a source of model error.
* **Uncertainty is the useful output today:** p10–p90 coverage is 80–83 % at h=1/7 (target 80 %),
  under-covering at h=14 (77 %) and for volatile VFPCK banana series (47–66 %).
* `market` carries ~60 % of the gain — the model mostly learns per-series drift.

**Recommendations for Phase 3+:** promote nothing that loses to naive (the gate in CLAUDE.md will
correctly keep naive-equivalent behaviour); add **arrival volumes** (Agmarknet publishes them; the
strongest known price driver, not stored in Phase 1) and leading-market signals; consider
forecasting only series with real movement, and serve the p10–p90 band prominently.
""")

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
nbf.write(nb, HERE / "02_backtest_report.ipynb")
print(f"wrote {HERE / '02_backtest_report.ipynb'} ({len(cells)} cells)")
