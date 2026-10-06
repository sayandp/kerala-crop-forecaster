# Phase 2.5 — signal hunt

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

## Results vs naive (52-fold walk-forward, h = 7, p50; same rows for model and naive)

| experiment | MAPE | naive MAPE | rel. vs naive % | DM p | verdict |
|---|---|---|---|---|---|
| E0 Phase-2 LGBM (reference) | 5.125 | 5.109 | -0.320 | 0.750 | no win |
| E1 + arrivals | 5.119 | 5.109 | -0.208 | 0.842 | no win |
| E2 + upstream markets | 5.125 | 5.109 | -0.325 | 0.717 | no win |
| E3 no market categorical | 5.108 | 5.109 | 0.005 | 0.900 | no win |
| E5 naive/LGBM combination | 5.338 | 5.346 | 0.157 | 0.913 | no win |

### Per crop

| experiment | crop | MAPE | naive | rel % | DM p | rule met |
|---|---|---|---|---|---|---|
| E0 | banana | 7.771 | 7.720 | -0.656 | 0.647 | no |
| E0 | coconut | 3.666 | 3.628 | -1.044 | 0.583 | no |
| E0 | pepper | 1.219 | 1.146 | -6.349 | 0.009 | no |
| E0 | rubber | 2.510 | 2.555 | 1.764 | 0.670 | no |
| E0 | tapioca | 4.533 | 4.630 | 2.097 | 0.203 | no |
| E1 | banana | 7.751 | 7.720 | -0.399 | 0.804 | no |
| E1 | coconut | 3.658 | 3.628 | -0.843 | 0.808 | no |
| E1 | pepper | 1.227 | 1.146 | -7.052 | 0.002 | no |
| E1 | rubber | 2.533 | 2.555 | 0.884 | 0.895 | no |
| E1 | tapioca | 4.537 | 4.630 | 2.009 | 0.231 | no |
| E2 | banana | 7.759 | 7.720 | -0.506 | 0.647 | no |
| E2 | coconut | 3.695 | 3.628 | -1.863 | 0.290 | no |
| E2 | pepper | 1.201 | 1.146 | -4.777 | 0.004 | no |
| E2 | rubber | 2.538 | 2.555 | 0.667 | 0.946 | no |
| E2 | tapioca | 4.537 | 4.630 | 2.005 | 0.284 | no |
| E3 | banana | 7.723 | 7.720 | -0.039 | 0.910 | no |
| E3 | coconut | 3.646 | 3.628 | -0.505 | 0.905 | no |
| E3 | pepper | 1.188 | 1.146 | -3.693 | 0.008 | no |
| E3 | rubber | 2.514 | 2.555 | 1.619 | 0.522 | no |
| E3 | tapioca | 4.593 | 4.630 | 0.809 | 0.594 | no |
| E5 | banana | 8.043 | 7.990 | -0.672 | 0.406 | no |
| E5 | coconut | 4.074 | 4.038 | -0.880 | 0.274 | no |
| E5 | pepper | 1.182 | 1.182 | -0.014 | 0.977 | no |
| E5 | rubber | 2.324 | 2.371 | 1.955 | 0.148 | no |
| E5 | tapioca | 4.902 | 5.083 | 3.550 | 0.046 | yes |

### E4a — move classification at h = 7 (up > +3 %, down < -3 %, flat)

DM p-values: `dm_p_*` = pre-agreed 0/1 loss; `dm_bal_p_*` = class-balanced 0/1 loss (supplementary, consistent with macro-F1).

| crop | n | share_up | share_down | macro_f1_lgbm | macro_f1_flat | macro_f1_trend | prec_up_lgbm | rec_up_lgbm | prec_down_lgbm | rec_down_lgbm | dm_p_vs_flat | dm_p_vs_trend | dm_bal_p_vs_flat | dm_bal_p_vs_trend |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 11579 | 0.231 | 0.206 | 0.520 | 0.240 | 0.410 | 0.403 | 0.446 | 0.350 | 0.551 | 0.886 | 1e-04 | 3e-62 | 3e-22 |
| banana | 4962 | 0.339 | 0.309 | 0.324 | 0.174 | 0.354 | 0.387 | 0.447 | 0.337 | 0.608 | 0.486 | 0.706 | 0.026 | 0.230 |
| coconut | 1786 | 0.231 | 0.206 | 0.484 | 0.240 | 0.370 | 0.405 | 0.465 | 0.349 | 0.372 | 0.453 | 0.004 | 1e-10 | 9e-07 |
| pepper | 1685 | 0.068 | 0.047 | 0.469 | 0.313 | 0.332 | 0.494 | 0.342 | 0.096 | 0.062 | 0.019 | 2e-04 | 3e-04 | 0.001 |
| rubber | 1027 | 0.147 | 0.122 | 0.560 | 0.282 | 0.371 | 0.433 | 0.384 | 0.390 | 0.512 | 0.425 | 0.010 | 3e-10 | 2e-04 |
| tapioca | 2119 | 0.147 | 0.130 | 0.618 | 0.280 | 0.378 | 0.460 | 0.479 | 0.461 | 0.629 | 0.084 | 2e-11 | 9e-27 | 1e-21 |

### E4b — weekly mean price, horizons 1-4 weeks (all crops)

| horizon_weeks | mape_lgbm | mape_naive | rel_improvement_pct | dm_p | wins |
|---|---|---|---|---|---|
| 1 | 3.835 | 3.794 | -1.072 | 0.075 | False |
| 2 | 5.761 | 5.647 | -2.008 | 0.102 | False |
| 3 | 7.175 | 7.012 | -2.316 | 0.070 | False |
| 4 | 8.260 | 8.124 | -1.678 | 0.346 | False |

Relative MAPE improvement vs naive weekly, per crop (negative = worse than naive):

| crop | rel % 1w | rel % 2w | rel % 3w | rel % 4w |
|---|---|---|---|---|
| banana | -1.2 | -1.9 | -1.3 | -0.0 |
| coconut | -0.1 | -5.5 | -10.2 | -10.3 |
| pepper | -3.4 | -4.6 | -4.3 | -6.4 |
| rubber | 1.2 | -1.0 | -0.9 | 2.7 |
| tapioca | -1.5 | 0.3 | 0.2 | -0.8 |

### E3 — where the importance goes without the `market` categorical (share of gain %)

| feature | with_market | without_market |
|---|---|---|
| roll_cv_7 | 4.37 | 44.69 |
| roll_cv_28 | 4.05 | 15.38 |
| spread | 1.71 | 6.80 |
| commodity | 0.81 | 5.71 |
| lag_14_rel | 1.50 | 5.44 |
| roll_mean_7_rel | 6.40 | 3.99 |
| roll_mean_28_rel | 4.79 | 3.17 |
| log_last | 2.95 | 2.32 |

### E5 — learned per-series weight on LGBM (mean over evaluated folds)

| commodity | market | variety | weight |
|---|---|---|---|
| banana | Chenkal VFPCK | Nendran | 0.00 |
| banana | Elamad VFPCK | Nendran | 0.21 |
| banana | Kayamkulam | Nendran | 0.66 |
| banana | Kunnukara VFPCK | Nendran | 0.31 |
| banana | Mookkannur VFPCK | Nendran | 0.82 |
| banana | Parassala | Nendran | 0.80 |
| banana | Thiruvaniyoor VFPCK | Nendran | 0.36 |
| banana | Vengannore VFPCK | Nendran | 0.90 |
| coconut | Koduvayoor | Big | 0.33 |
| coconut | North Paravur | Big | 0.45 |
| coconut | Palakkad | Coconut | 0.00 |
| pepper | Kannur | Other | 0.00 |
| pepper | Manjeswaram | Garbled Other | 0.05 |
| pepper | North Paravur | Garbled | 0.00 |
| rubber | Kalpetta | RSS-4 | 0.10 |
| rubber | Pulpally | Other | 0.56 |
| tapioca | Manjeswaram | Other | 0.94 |
| tapioca | North Paravur | Other | 0.00 |
| tapioca | Payyannur | Other | 0.00 |
| tapioca | Perumbavoor | Tapioca | 0.17 |

## Neon storage after archiving

DB size: **305.2 MB → 137.1 MB** (target < 220 MB). Archived: [{'release_tag': 'data-archive-2026-10-07', 'cutoff_date': '2026-07-09', 'rows': 719276, 'archived_at': '2026-10-06 21:31:45.451436+00:00'}].

| table | total_mb | heap_mb | index_mb | live_rows |
|---|---|---|---|---|
| prices_clean | 110.5234375000000000 | 72.3593750000000000 | 38.1093750000000000 | 747337 |
| prices_rejected | 6.5468750000000000 | 5.4375000000000000 | 1.1015625000000000 | 35636 |
| prices_raw | 6.0937500000000000 | 3.6250000000000000 | 2.4609375000000000 | 28057 |
| weather_daily | 5.8984375000000000 | 4.0546875000000000 | 1.8046875000000000 | 44828 |
| pipeline_runs | 0.07812500000000000000 | 0.01562500000000000000 | 0.03125000000000000000 | 13 |
| model_metrics | 0.07812500000000000000 | 0.03125000000000000000 | 0.01562500000000000000 | 234 |
| variety_aliases | 0.04687500000000000000 | 0.00781250000000000000 | 0.03125000000000000000 | 19 |
| archive_log | 0.03125000000000000000 | 0.00781250000000000000 | 0.01562500000000000000 | 1 |
| forecasts | 0.02343750000000000000 | 0E-24 | 0.01562500000000000000 | 0 |
| subscribers | 0.01562500000000000000 | 0E-24 | 0.00781250000000000000 | 0 |

Indexes:

| table | index | mb |
|---|---|---|
| prices_clean | prices_clean_pkey | 38.1093750000000000 |
| weather_daily | weather_daily_pkey | 1.8046875000000000 |
| prices_raw | prices_raw_pkey | 1.4843750000000000 |
| prices_raw | ix_prices_raw_series | 0.97656250000000000000 |
| prices_rejected | prices_rejected_pkey | 0.78125000000000000000 |
| prices_rejected | ix_prices_rejected_date | 0.32031250000000000000 |
| archive_log | archive_log_pkey | 0.01562500000000000000 |
| pipeline_runs | pipeline_runs_pkey | 0.01562500000000000000 |
| pipeline_runs | ix_pipeline_runs_status | 0.01562500000000000000 |
| model_metrics | model_metrics_pkey | 0.01562500000000000000 |
| variety_aliases | variety_aliases_pkey | 0.01562500000000000000 |
| variety_aliases | variety_aliases_commodity_market_raw_variety_valid_from_val_key | 0.01562500000000000000 |
| forecasts | forecasts_pkey | 0.00781250000000000000 |
| subscribers | subscribers_pkey | 0.00781250000000000000 |
| forecasts | ix_forecasts_target | 0.00781250000000000000 |

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
