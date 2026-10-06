*Run 2026-10-07 on Neon data to 2026-10-07 (20 series incl. rubber Kalpetta RSS-4). MLflow:
parent run `phase2.5-signal-hunt` (experiment `cropcast-backtest`, DagsHub) with one child run
per experiment. Raw results: `reports/phase2_5/`.*

**Yardstick.** 52-fold walk-forward diagnostic at h = 7 (14-day folds, ≈ 2 years, 11,579
forecasts), p50 only; model and naive scored on identical rows.

**Decision rule (fixed before running).** An approach *wins* only if it beats naive by ≥ 3 %
relative MAPE **and** a Diebold–Mariano test gives p < 0.05 in its favour (E4a: macro-F1 must
beat both baselines, plus DM p < 0.05). DM: APE loss (0/1 loss for E4a), loss differential
averaged across series per target date, Newey–West variance with h − 1 lags, Harvey–Leybourne–
Newbold correction, two-sided p.

## Verdicts

| experiment | verdict |
|---|---|
| E0 reference (Phase-2 LGBM) | **no win** — −0.3 %, p = 0.75; pepper significantly *worse* than naive (p = 0.009) |
| E1 arrivals | **no win** — −0.2 %, p = 0.84. Arrival features 98.5–100 % populated but carry no signal (3 % of gain; Spearman with next-week change −0.01) |
| E2 upstream TN/KA markets | **no win** — −0.3 %, p = 0.72. Weak correlations only (coconut 0.08, pepper 0.06); TN banana/tapioca exist only from 2024-06 |
| E3 no `market` categorical | **no win** — +0.005 %, p = 0.90: *exactly* naive. Importance moves from `market` to volatility (roll_cv_7 45 %): Phase-2 "market" gain was memorisation |
| E4a move classification | **partial win, rule not met.** Macro-F1 0.52 vs 0.24 (flat) / 0.41 (trend). DM on 0/1 loss: p = 1e-4 vs trend, p = 0.89 vs always-flat (equal accuracy 56.5 vs 56.4 %). Supplementary class-balanced DM: significant vs both overall and for coconut, pepper, rubber, tapioca (not banana vs trend) |
| E4b weekly mean, 1–4 weeks | **no win** — worse than naive weekly at every horizon (−1.1 … −2.3 %), coconut significantly worse at 2–3 weeks |
| E5 per-series combination | **no win overall** (+0.16 %, p = 0.91). **Tapioca alone meets the rule** (+3.6 %, p = 0.046) — one of five per-crop tests, not significant after a Bonferroni correction (needs p < 0.01) |

**Bottom line:** no approach forecasts the *price level* better than "last price" at 1–2 weeks.
The only robust signal found is **direction of large moves** (E4a), for every crop except banana.

<!-- TABLES -->

## Recommendation for Phase 3

* **Champion for all five crops: naive** (last observed price) for the p50 point forecast.
  This is what users see in Phase 3; it is honest and every alternative tested loses or ties.
* **Uncertainty band:** keep serving LightGBM's p10–p90 band around the naive point (Phase 2:
  80–83 % coverage at h = 1/7). Re-check coverage live.
* **Challenger (shadow, logged daily, not user-facing): the E4a move classifier** for coconut,
  pepper, rubber, tapioca — it is the only model with evidence of skill, and "price likely to
  rise/fall > 3 % this week" maps directly onto the planned Telegram alerts. Promote to
  user-facing alerts only if live results meet the decision rule (incl. a pre-registered
  class-balanced DM test vs always-flat, which this report shows is the appropriate loss).
* **Banana:** naive only. No approach found signal (E4a does not beat trend persistence).
* **LGBM price regressor:** keep in the pipeline as the registered challenger under the
  existing gate (it will correctly never be promoted while it ties naive); tapioca's E5
  combination stays in shadow until it holds up on live data with a correction for testing
  five crops.
* **Data:** keep ingesting arrivals (cheap, now stored) and consider adding the TN/KA upstream
  feeds to the daily pull only if a future model needs them — today they do not pay for
  their ~7 extra requests/day.

## Storage changes made in this phase

* prices_raw rows older than 90 days (719,276 rows, 2018-01-01 → 2026-07-08) archived to the
  GitHub Release `data-archive-2026-10-07` (9 yearly parquet assets, 4.9 MB, downloaded back
  and verified by per-year row count + modal checksum before deletion), then deleted from Neon
  and `VACUUM FULL`. Local dev DB keeps everything. A monthly `archive` step (scheduled run on
  the 1st) does the same for rows ageing past 90 days; `clean --full` reads the releases back.
* Arrivals stored (migration 004) and backfilled 2018→ by exact match from the cached
  Agmarknet responses (100 % of prices_raw rows).

## Assumptions / caveats

* Migration for arrivals is **004** (003 had already been applied everywhere; a numbered
  migration is the safe way to add columns). archive_log is migration 005 (small new table).
* E4a's DM on plain 0/1 loss is dominated by the majority "flat" class; the class-balanced
  variant was added after seeing results and is reported as supplementary, not as the verdict.
* Per-crop tests are not corrected for multiple comparisons (5 crops); the overall rows are
  the primary result.
* The 52-fold diagnostic is p50-only and evaluates ~2 years; Phase-2's official 5-fold metrics
  are unchanged.
