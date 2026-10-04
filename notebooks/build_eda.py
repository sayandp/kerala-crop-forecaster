"""Builds notebooks/eda.ipynb (kept as code so the notebook diff is reviewable).

    uv run python notebooks/build_eda.py
    uv run jupyter nbconvert --to notebook --execute --inplace notebooks/eda.ipynb
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
# Kerala crop prices — Phase 1 EDA

Which crop × market series are good enough to model? Data: `prices_raw` (Agmarknet,
Rs./quintal, validated), backfilled from 2018 plus the daily pull.

**Usable series rule:** span ≥ 2 years, < 20 % missing *trading* days (Mon–Sat; Kerala
mandis rarely trade on Sundays, so calendar-day gaps would overstate missingness), and
still alive (last observation ≤ 30 days before the latest date in the table).
""")

code("""
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy import text
from cropcast.db import get_engine

warnings.filterwarnings("ignore", category=FutureWarning)
pd.set_option("display.width", 160, "display.max_columns", 20, "display.max_rows", 80)

# Categorical palette (validated, fixed order): one hue per crop, never re-ordered.
CROP_COLORS = {"banana": "#2a78d6", "coconut": "#eb6834", "rubber": "#1baf7a",
               "pepper": "#eda100", "tapioca": "#e87ba4"}
INK, MUTED, GRID = "#0b0b0b", "#898781", "#e6e5e0"
plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "axes.axisbelow": True, "lines.linewidth": 1.2, "font.size": 9,
    "axes.titlesize": 10, "axes.titleweight": "bold", "legend.frameon": False,
})

eng = get_engine()
df = pd.read_sql(text("SELECT date, district, market, commodity, variety, min_price, "
                      "max_price, modal_price, source FROM prices_raw"), eng,
                 parse_dates=["date"])
for c in ("min_price", "max_price", "modal_price"):
    df[c] = df[c].astype(float)
LATEST = df["date"].max()
print(f"{len(df):,} rows | {df.date.min():%Y-%m-%d} → {LATEST:%Y-%m-%d} | "
      f"{df.market.nunique()} markets | sources: {df.source.value_counts().to_dict()}")
""")

md("## 1. Volume per crop")
code("""
summary = (df.groupby("commodity")
             .agg(rows=("modal_price", "size"), first=("date", "min"), last=("date", "max"),
                  markets=("market", "nunique"), varieties=("variety", "nunique"))
             .sort_values("rows", ascending=False))
summary
""")
code("""
(df.groupby(["commodity", "variety"]).size().rename("rows").reset_index()
   .sort_values(["commodity", "rows"], ascending=[True, False])
   .groupby("commodity").head(6).set_index(["commodity", "variety"]))
""")

code("""
fig, axes = plt.subplots(5, 1, figsize=(10, 7), sharex=True)
for ax, crop in zip(axes, CROP_COLORS):
    m = df[df.commodity == crop].groupby(pd.Grouper(key="date", freq="MS")).size()
    ax.bar(m.index, m.values, width=25, color=CROP_COLORS[crop])
    ax.set_title(f"{crop}: rows per month", loc="left")
    ax.set_ylabel("rows")
fig.tight_layout()
""")

md("""
## 2. Coverage matrix

A *series* is (commodity, market, variety): the varieties are different products with
different price levels (Nendran vs Robusta banana differ ~2×), so they must not be pooled.
""")
code("""
def trading_days(start, end):
    days = pd.date_range(start, end, freq="D")
    return int((days.dayofweek != 6).sum())   # Mon–Sat

g = df.groupby(["commodity", "market", "variety"])
cov = g.agg(n_days=("date", "nunique"), first=("date", "min"), last=("date", "max"),
            median_price=("modal_price", "median")).reset_index()
cov["span_years"] = (cov["last"] - cov["first"]).dt.days / 365.25
cov["expected"] = [trading_days(a, b) for a, b in zip(cov["first"], cov["last"])]
cov["pct_missing"] = (1 - cov["n_days"] / cov["expected"]).clip(lower=0) * 100
cov["days_since_last"] = (LATEST - cov["last"]).dt.days
cov["usable"] = (cov.span_years >= 2) & (cov.pct_missing < 20) & (cov.days_since_last <= 30)
print(f"{len(cov)} series, {cov.usable.sum()} usable")
cov.groupby("commodity").agg(series=("usable", "size"), usable=("usable", "sum"),
                             best_missing_pct=("pct_missing", "min")).round(1)
""")

code("""
def show(d):
    return (d.assign(first=d["first"].dt.date, last=d["last"].dt.date)
             .round({"span_years": 1, "pct_missing": 1, "median_price": 0})
             .drop(columns=["expected"]))

# Top 8 series per crop by coverage (usable ones first).
top = (cov.sort_values(["commodity", "usable", "pct_missing"], ascending=[True, False, True])
          .groupby("commodity").head(8))
show(top).style.apply(
    lambda r: ["background-color: #d9f2e6" if r.usable else ""] * len(r), axis=1
).format(precision=1)
""")

code("""
# Near misses: alive, ≥ 2 years, but 20–40 % missing (candidates if gaps are tolerable).
show(cov[(~cov.usable) & (cov.span_years >= 2) & (cov.days_since_last <= 30)
         & (cov.pct_missing < 40)].sort_values(["commodity", "pct_missing"]))
""")

code("""
# Heat strip: % of trading days observed per month, best 6 series per crop.
best = (cov.sort_values(["commodity", "usable", "pct_missing"], ascending=[True, False, True])
           .groupby("commodity").head(6))
keys = list(best[["commodity", "market", "variety"]].itertuples(index=False, name=None))
months = pd.date_range(df.date.min().to_period("M").start_time, LATEST, freq="MS")
trade_per_month = pd.Series({m: trading_days(m, m + pd.offsets.MonthEnd(0)) for m in months})
mat = []
for k in keys:
    s = df[(df.commodity == k[0]) & (df.market == k[1]) & (df.variety == k[2])]
    obs = s.groupby(s.date.dt.to_period("M").dt.start_time)["date"].nunique()
    mat.append((obs.reindex(months).fillna(0) / trade_per_month).clip(0, 1).values)
fig, ax = plt.subplots(figsize=(11, 0.28 * len(keys) + 1))
ax.imshow(np.array(mat), aspect="auto", cmap="Blues", vmin=0, vmax=1, interpolation="nearest")
ax.set_yticks(range(len(keys)), [f"{c} · {m} · {v}" for c, m, v in keys], fontsize=7)
yr = [i for i, m in enumerate(months) if m.month == 1]
ax.set_xticks(yr, [months[i].year for i in yr]); ax.grid(False)
ax.set_title("Share of trading days observed per month (darker = fuller)", loc="left")
fig.tight_layout()
""")

md("## 3. Price history — best series per crop")
code("""
pick = (cov[(cov.n_days > 200) & (cov.days_since_last <= 400)].sort_values(["commodity", "usable", "pct_missing"],
                                         ascending=[True, False, True])
           .groupby("commodity").head(3))
fig, axes = plt.subplots(5, 1, figsize=(11, 13), sharex=True)
for ax, crop in zip(axes, CROP_COLORS):
    rows = pick[pick.commodity == crop]
    shades = [CROP_COLORS[crop], "#52514e", "#898781"]
    for (_, r), col in zip(rows.iterrows(), shades):
        s = (df[(df.commodity == crop) & (df.market == r.market) & (df.variety == r.variety)]
               .set_index("date")["modal_price"].sort_index())
        ax.plot(s.index, s.values, color=col, lw=1.0, label=f"{r.market} · {r.variety}")
    ax.set_title(f"{crop} — modal price (Rs./quintal)", loc="left")
    ax.legend(loc="upper left", fontsize=7)
fig.tight_layout()
""")

md("## 4. Seasonality")
code("""
# Month-of-year: price relative to each series' own yearly mean, averaged over usable series
# (falls back to the 5 best-covered series when a crop has none usable).
base = cov[cov.usable]
for crop in CROP_COLORS:
    if (base.commodity == crop).sum() == 0:
        base = pd.concat([base, cov[cov.commodity == crop].nsmallest(5, "pct_missing")])
sel = df.merge(base[["commodity", "market", "variety"]], on=["commodity", "market", "variety"])
sel["year"] = sel.date.dt.year
sel["rel"] = sel.modal_price / sel.groupby(["commodity", "market", "variety", "year"])[
    "modal_price"].transform("mean")
moy = sel.groupby(["commodity", sel.date.dt.month])["rel"].mean().unstack(0)
dow = sel.groupby(["commodity", sel.date.dt.dayofweek])["rel"].mean().unstack(0)
dow_n = sel.groupby(sel.date.dt.dayofweek).size()

fig, axes = plt.subplots(2, 5, figsize=(13, 5), sharey="row")
for i, crop in enumerate(CROP_COLORS):
    axes[0, i].bar(moy.index, moy[crop] - 1, color=CROP_COLORS[crop], width=0.7)
    axes[0, i].axhline(0, color=MUTED, lw=0.8)
    axes[0, i].set_title(crop, loc="left"); axes[0, i].set_xticks(range(1, 13, 2))
    axes[0, i].set_xlim(0.5, 12.5); axes[1, i].set_xlim(-0.5, 6.5)
    axes[1, i].bar(dow.index, dow[crop] - 1, color=CROP_COLORS[crop], width=0.7)
    axes[1, i].axhline(0, color=MUTED, lw=0.8)
    axes[1, i].set_xticks(range(7), list("MTWTFSS"))
axes[0, 0].set_ylabel("month: vs yearly mean")
axes[1, 0].set_ylabel("weekday: vs yearly mean")
axes[0, 0].yaxis.set_major_formatter(lambda v, _: f"{v:+.0%}")
axes[1, 0].yaxis.set_major_formatter(lambda v, _: f"{v:+.0%}")
fig.tight_layout()
print("observations by weekday (Mon=0):", dow_n.to_dict())
(moy - 1).mul(100).round(1).T
""")

md("""
### Onam / Vishu windows

Festival dates (Thiruvonam; Vishu) are hard-coded here for the EDA only — Phase 2 moves
them to `features/festivals.yaml`. Event study: price relative to the mean of days −45…−22
before the festival, averaged over years and the best-covered series.
""")
code("""
ONAM = ["2018-08-25", "2019-09-11", "2020-08-31", "2021-08-21", "2022-09-08",
        "2023-08-29", "2024-09-15", "2025-09-05", "2026-08-26"]
VISHU = ["2018-04-14", "2019-04-15", "2020-04-14", "2021-04-14", "2022-04-15",
         "2023-04-15", "2024-04-14", "2025-04-14", "2026-04-15"]

def event_study(crop, days, lo=-45, hi=21):
    rows = []
    series = base[base.commodity == crop]
    for _, r in series.iterrows():
        s = (df[(df.commodity == crop) & (df.market == r.market) & (df.variety == r.variety)]
               .set_index("date")["modal_price"])
        for d in pd.to_datetime(days):
            w = s[(s.index >= d + pd.Timedelta(days=lo)) & (s.index <= d + pd.Timedelta(days=hi))]
            ref = w[w.index <= d + pd.Timedelta(days=-22)].mean()
            if len(w) < 20 or not np.isfinite(ref):
                continue
            rows.append(pd.DataFrame({"k": (w.index - d).days, "rel": w.values / ref - 1}))
    if not rows:
        return pd.Series(dtype=float)
    return pd.concat(rows).groupby("k")["rel"].mean().rolling(5, center=True, min_periods=1).mean()

fig, axes = plt.subplots(1, 2, figsize=(12, 3.6), sharey=True)
for ax, (name, days) in zip(axes, [("Onam", ONAM), ("Vishu", VISHU)]):
    for crop in CROP_COLORS:
        es = event_study(crop, days)
        if len(es):
            ax.plot(es.index, es.values, color=CROP_COLORS[crop], label=crop)
    ax.axvline(0, color=MUTED, lw=0.8, ls="--")
    ax.set_title(f"{name}: price vs pre-festival baseline (5-day smoothed)", loc="left")
    ax.set_xlabel("days from festival"); ax.yaxis.set_major_formatter(lambda v, _: f"{v:+.0%}")
axes[0].legend(fontsize=8)
fig.tight_layout()
pd.DataFrame({crop: {f"{n} peak (-14..0)": event_study(crop, d).loc[-14:0].max() * 100
                     for n, d in [("Onam", ONAM), ("Vishu", VISHU)]}
              for crop in CROP_COLORS}).round(1)
""")

md("""
## 5. Outliers

Rule: a price more than 50 % above or below its series' centred 15-observation rolling
median (|log ratio| > log 1.5). A MAD-based z-score was tried first but explodes on the
many series whose price is flat for weeks (MAD ≈ 0), so it is not used.
""")
code("""
parts = []
for (c, m, v), s in df.sort_values("date").groupby(["commodity", "market", "variety"]):
    if len(s) < 60:
        continue
    lp = np.log(s["modal_price"].to_numpy())
    med = pd.Series(lp).rolling(15, center=True, min_periods=5).median().to_numpy()
    parts.append(pd.DataFrame({"commodity": c, "market": m, "variety": v,
                               "date": s["date"].to_numpy(),
                               "modal_price": s["modal_price"].to_numpy(),
                               "ratio_to_median": np.exp(lp - med)}))
zz = pd.concat(parts, ignore_index=True)
out = zz[np.abs(np.log(zz.ratio_to_median)) > np.log(1.5)]
print(f"{len(out):,} outliers ({len(out) / len(zz):.2%} of rows in series with ≥ 60 obs)")
display(out.groupby("commodity").size().rename("outliers").to_frame()
          .join(zz.groupby("commodity").size().rename("rows"))
          .assign(pct=lambda d: (d.outliers / d.rows * 100).round(2)))
out.assign(dev=np.abs(np.log(out.ratio_to_median))).sort_values("dev", ascending=False)    .drop(columns="dev").head(15).round({"ratio_to_median": 2})
""")

code("""
# Day-over-day jumps > 50 % between consecutive observations (≤ 3 days apart).
jumps = []
for (c, m, v), s in df.sort_values("date").groupby(["commodity", "market", "variety"]):
    s = s.set_index("date")["modal_price"]
    gap = s.index.to_series().diff().dt.days
    ch = s.pct_change()
    j = ch[(gap <= 3) & (ch.abs() > 0.5)]
    jumps += [(c, m, v, d, x) for d, x in j.items()]
jumps = pd.DataFrame(jumps, columns=["commodity", "market", "variety", "date", "pct_change"])
print(f"{len(jumps)} jumps > 50 % in ≤ 3 days")
jumps.groupby("commodity").size()
""")

md("## 6. Data-quality issues from the contract")
code("""
rej = pd.read_sql(text("SELECT commodity, market, reason, min_price, max_price, modal_price "
                       "FROM prices_rejected"), eng)
print(f"{len(rej):,} quarantined rows vs {len(df):,} loaded "
      f"({len(rej) / (len(rej) + len(df)):.1%})")
r = rej.assign(reason=rej.reason.str.split(";")).explode("reason")
display(r.groupby(["reason", "commodity"]).size().unstack(fill_value=0))
zero = rej[(rej.min_price == 0) & (rej.max_price == 0)]
print(f"min=max=0 (modal-only reports): {len(zero):,} rows, "
      f"{zero.market.str.contains('VFPCK').mean():.0%} from VFPCK markets")
dup = rej[rej.reason.str.contains("duplicate_key")]
print(f"duplicate keys (grade-level repeats): {len(dup):,} rows, "
      f"{dup.market.str.contains('VFPCK').mean():.0%} from VFPCK markets")
""")

code("""
# Spread sanity: min–max spread as % of modal, by crop (wide spreads = mixed grades).
d = df.assign(spread=(df.max_price - df.min_price) / df.modal_price * 100)
d.groupby("commodity")["spread"].describe(percentiles=[0.5, 0.9, 0.99]).round(1)
""")

md("""
## 7. Series that ended around the Agmarknet 2.0 cut-over

Agmarknet 2.0's combined price+arrival data starts 2025-11-07. Markets keep reporting
overall (≈ 250–275 markets/week either side), but some long crop × market series stop
right there — a live model must not depend on them.
""")
code("""
long = cov[cov.n_days >= 500]
ended = long[(long["last"] >= "2025-10-25") & (long["last"] <= "2025-11-20")]
print(f"{len(ended)} of {len(long)} series with ≥ 500 obs ended 2025-10-25…2025-11-20")
show(ended.sort_values("n_days", ascending=False)).head(15)
""")

md("## 8. Recommended modelling set (rule-based, reproducible)")
code("""
RULES = {  # crop -> (variety filter or None, max series)
    "banana": ("Nendran", 8), "coconut": (None, 3), "pepper": (None, 3),
    "tapioca": (None, 4), "rubber": (None, 2),
}
rec = []
for crop, (variety, k) in RULES.items():
    c = cov[cov.commodity == crop]
    if variety:
        c = c[c.variety == variety]
    usable = c[c.usable].sort_values("pct_missing").head(k).assign(tier="usable")
    if len(usable) == 0:  # no series passes: take the best alive near-misses (≤ 30 % missing)
        usable = (c[(c.span_years >= 2) & (c.days_since_last <= 30) & (c.pct_missing <= 30)]
                  .sort_values("pct_missing").head(k).assign(tier="provisional"))
    rec.append(usable)
rec = pd.concat(rec)
show(rec[["commodity", "market", "variety", "district" if "district" in rec else "market",
          "n_days", "first", "last", "span_years", "pct_missing", "median_price", "tier",
          "expected"]].loc[:, lambda d: ~d.columns.duplicated()])
""")


md("""
## 9. Conclusions — recommended series and data issues

*Numbers below are from the run on 2026-10-04 (prices_raw: 743,947 rows, 2018-01-01 → 2026-10-03,
303 markets; 35,576 rows quarantined = 4.6 %).*

### Recommended modelling set (19 series; output of section 8)

| crop | series (market · variety) | notes |
|---|---|---|
| **banana** (Nendran) | Kayamkulam · Nendran (8.8 y), Chenkal VFPCK, Mookkannur VFPCK, Parassala, Thiruvaniyoor VFPCK, Elamad VFPCK, Kunnukara VFPCK, Vengannore VFPCK | Only Kayamkulam has 8+ years; the VFPCK series start 2024-03/04 (≈ 2.5 y). 71 banana series pass the rule — plenty of room to add more. |
| **coconut** | Koduvayoor · Big, Palakkad · Coconut, North Paravur · Big | Usable history starts 2021-12 at best. |
| **pepper** | Kannur · Other (8.8 y, 1 % missing), Manjeswaram · Garbled Other, North Paravur · Garbled | North Paravur is ~1.7× the others' price level (garbled premium) and step-like; keep it as its own series. |
| **tapioca** | Manjeswaram · Other, Payyannur · Other, Perumbavoor · Tapioca, North Paravur · Other | Manjeswaram is very noisy since 2024 (daily swings ±40 %). |
| **rubber** | *provisional:* Pulpally · Other (25.7 % missing) | **No rubber series passes the rule.** No Kottayam (benchmark) series exists in Agmarknet at all. Kalpetta (12.7 % missing) was relabelled Other → RSS-4 at the Agmarknet 2.0 cut-over; stitched, it would qualify. Rubber Board data is the real fix. |

### Seasonality & festivals (relative to each series' own yearly mean)
* **banana:** strong — +14 % in August, −7 % in March; Onam event study shows ≈ +13 % over the
  two weeks before Thiruvonam, unwinding within ~2 weeks after. Vishu ≈ +5–9 %.
* **coconut:** annual cycle, trough May–Jun (−7 %), peak Nov–Dec (+10–15 %). The post-Onam rise
  is this seasonal climb, not an Onam effect.
* **pepper / rubber:** weak seasonality; mostly trend (pepper 30k → 68k Rs./q since 2020; rubber
  ~13k → 25k). Rubber Jan −8 %, Aug +6 %.
* **tapioca:** mild (Sep–Oct +5 %); Vishu +9 %.
* **Day of week:** no meaningful price effect; Sunday has ~40 % of a weekday's observations.

### Data issues found
1. **Grade-level duplicates** — 32,502 rows (4.2 % of all rows), almost all banana, 55 % from VFPCK markets:
   same market/variety/day reported twice with different prices (e.g. 1,400 vs 2,400). The
   report API has no grade column; the contract keeps the first row. → Phase 2: decide on a
   deterministic rule (e.g. arrivals-weighted mean) or use the grade-aware report.
2. **Modal-only reports** — 2,613 rows with min = max = 0 (99 % VFPCK) are quarantined by
   `min ≤ modal ≤ max`. Making min/max nullable would recover them (schema change — needs sign-off).
3. **Price-scale errors pass the contract** — e.g. banana at Rs. 2–3/q (Perinthalmanna 2018-03),
   Rs. 0.3/q, a Venmony VFPCK Nendran series around Rs. 65/q (per-kg entered as per-quintal),
   rubber spikes to 48k vs 15k. 0.88 % of rows are > 50 % from their local median.
   → Phase 2: add per-crop plausibility bands to the contract.
4. **Agmarknet 2.0 cut-over (≈ 2025-11-07)** — 58 of 450 long series end there; 22 continue under
   a new variety label (green banana Other → Green, rubber Other → RSS-4), 28 genuinely stop.
   → Phase 2: a variety-alias table applied *before* series selection.
5. **Missing-days metric is optimistic for VFPCK markets**, which trade on Sundays (Mon–Sat
   expectation, clipped at 0 %).
6. **Rubber / pepper coverage** — 18 rubber and 37 pepper markets in total, none in Kottayam;
   Rubber Board and Spices Board feeds would add the benchmark series (no stable public API found).
7. **History** — Agmarknet 2.0 serves prices from 2018-01; data before 2018 was not attempted.
""")

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
nbf.write(nb, HERE / "eda.ipynb")
print(f"wrote {HERE / 'eda.ipynb'} ({len(cells)} cells)")
