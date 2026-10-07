# Pre-registration — E4a move classifier (live shadow evaluation)

*Written and committed 2026-10-07, before any shadow prediction exists. This file is the
contract for judging the challenger; it may not be edited after the first shadow prediction
except to append dated clarifications that do not change any test, threshold or window.*

## 1. Challenger

- **Model:** E4a up / down / flat classifier, horizon **h = 7 days** — registered as
  `cropcast-move-h7`, alias `challenger`.
- **Classes:** realised move `m = price(target_date) / last_value(forecast time) − 1`;
  **up** if `m > +3 %`, **down** if `m < −3 %`, else **flat**.
- **Crops judged:** coconut, pepper, rubber, tapioca (all their series in `config/series.yaml`).
  **Banana excluded** (no evidence of skill in Phase 2.5).
- **Specification (the "spec"):** features = `cropcast.features.build.FEATURE_COLUMNS` for h = 7;
  LightGBM multiclass, `class_weight="balanced"`, `cropcast.models.lgbm.DEFAULT_PARAMS`,
  seed 42, early stopping on the last 28 days of the training window, then refit with the best
  iteration count; trained on all 20 modelled series. Each shadow prediction stores the
  **spec hash** (hash of feature list, parameters, thresholds, training scope and classifier
  code version).
- **Retraining:** weekly refits on new data **with an identical spec** are part of the
  challenger. **Any change to the spec resets the evaluation window** (only predictions with the
  current spec hash count).

## 2. Data that counts

- **Only live shadow predictions made after this commit** (the shadow step refuses to run
  unless this file is committed; each row records this file's commit SHA).
- Unit: one prediction per series per forecast date whose **target-date price is observed** in
  `prices_clean` (missing market days are excluded, never imputed).
- Backtests (Phase 2.5 or later) are **never** used for this verdict.

## 3. Primary test (per crop)

- **Loss:** class-balanced 0/1 loss. For each crop, class weights `w_c = 1 / (3 · p_c)` where
  `p_c` is the realised share of class `c` among that crop's evaluated predictions; loss = `w_c`
  if wrong, 0 if right.
- **Comparisons:** challenger vs **always-flat**, and challenger vs **trend persistence**
  (class of the series' 7-day change at forecast time, same ±3 % thresholds; recorded with the
  prediction).
- **Diebold–Mariano:** loss differential averaged across the crop's series per target date;
  zero-mean test with **Newey–West (HAC) variance, lag 6**; Harvey–Leybourne–Newbold correction;
  two-sided p from Student-t (T − 1); the statistic must favour the challenger.
- **Multiple testing:** **Holm** correction across the 4 crops, applied separately to each
  baseline comparison; **α = 0.05**. A crop is significant only if it survives Holm against
  **both** baselines.

## 4. Practical bar (per crop)

- Precision of **up** calls ≥ **55 %** AND ≥ realised up base rate **+ 10 pp**.
- Precision of **down** calls ≥ **55 %** AND ≥ realised down base rate **+ 10 pp**.

## 5. Minimum evidence (per crop)

- ≥ **12 weeks** of matured shadow data (≥ 84 days between the first and last evaluated target
  date) **AND** ≥ **30 realised moves** with |m| > 3 %.
- Before both hold, the verdict is **"insufficient data"** — no test is reported as pass/fail.

## 6. Verdict

- **pass** = minimum evidence met AND Holm-significant vs both baselines AND practical bar met.
- **fail** = minimum evidence met and any of the above not met.
- A pass sets the MLflow alias `champion_<crop>` on the classifier version and notifies the
  admin. **It does not enable user-facing alerts**; that is a manual config flag.
- The check runs weekly (`promotion_check` step) and logs every verdict to MLflow and the
  `promotion_log` table.

## 7. Why this test (disclosure)

The class-balanced loss was chosen **after** seeing the Phase 2.5 backtest (plain 0/1 loss was
dominated by the majority "flat" class: accuracy 56.5 % vs 56.4 % for always-flat, while
macro-F1 was 0.52 vs 0.24). Because the choice was informed by those results, the classifier is
judged **only on new, live data** under this pre-registered test.

---

## Amendment 1 — 2026-10-07 (clarifications; no test, threshold or window changed)

*Written when 12 shadow predictions existed (all made 2026-10-07, first target date
2026-10-14): **no outcome had matured**, so nothing observed could inform these clarifications.*

Already stated in the original text (commit `cf555f5`), restated here for completeness:

- **Class weights:** `w_c = 1 / (3 · p_c)`, `p_c` = realised share of class `c` among the crop's
  evaluated predictions (§3).
- **Holm per baseline:** Holm across the 4 crops, applied separately to the always-flat and the
  trend-persistence comparison; a crop must survive both (§3).
- **Spec-hash window:** only predictions whose spec hash equals the current spec count; any spec
  change resets the window; identical-spec weekly refits continue it (§1).

New clarifications (implemented in `cropcast.monitor.live`, matching the code that ran from the
first shadow prediction):

- **Undefined test = p = 1:** if a crop's DM statistic is undefined (fewer than 10 distinct matured
  target dates, or a zero-variance loss differential), its p-value enters the Holm procedure as
  **1** (conservative), so it can never be "significant".
- **DM minimum:** the DM test is computed only with ≥ 10 distinct matured target dates; this is
  far below the ≥ 12-week minimum evidence, so it never decides a verdict on its own.
