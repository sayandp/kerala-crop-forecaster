# CLAUDE.md — Kerala Crop Price Forecaster

Self-retraining MLOps system that forecasts daily mandi (modal) prices for Kerala crops — banana (Nendran), coconut, rubber (RSS-4), pepper, tapioca — and pushes price alerts to farmers/traders via Telegram.

**Goal of the project:** a production-grade, end-to-end MLOps portfolio piece with real users. Every design choice should favour reliability, reproducibility and honest metrics over cleverness.

---

## Architecture (one-line summary)

GitHub Actions cron (daily 19:47 IST) → ingest → validate → features → train challenger → backtest vs baselines → promotion gate (MLflow registry) → batch predict with `@champion` → Postgres → served read-only by FastAPI (Render) / Next.js dashboard (Vercel, ISR) / Telegram. Evidently monitors drift (weekly); live MAPE is computed as actuals arrive.

**Serving is batch, not real-time.** Forecasts are precomputed nightly and read from Postgres. Do not add online inference.

## Stack

- Python 3.11, `uv` for deps (`pyproject.toml` + `uv.lock`)
- pandas, numpy, LightGBM, scikit-learn, Pandera
- MLflow (tracking + model registry, hosted on DagsHub)
- Postgres (Neon/Supabase in prod, docker-compose locally), SQLAlchemy 2.x + psycopg
- FastAPI + Uvicorn + slowapi (read-only API on Render); python-telegram-bot later (webhook inside FastAPI)
- Dashboard: Next.js (App Router, TypeScript strict, Tailwind, Recharts) in `web/`, pnpm, on Vercel; PWA;
  Playwright + @axe-core/playwright (dev only) for smoke / accessibility tests
- Evidently (drift reports)
- GitHub Actions (CI, daily pipeline, deploy); Prefect-compatible task/flow structure
- Docker, ruff, mypy, pytest

## Repo layout

```
src/cropcast/
  config.py            # pydantic-settings; ALL env vars read here only
  ingest/              # agmarknet.py, rubberboard.py, weather.py
  validate/schemas.py  # Pandera schemas (data contracts)
  clean/               # aliases.py (guarded variety renames), build.py (prices_clean)
  features/build.py    # feature engineering — single source of truth
  features/series.py   # loads config/series.yaml (the modelled series)
  features/snapshot.py # one prices_clean + weather read -> data/snapshots/*.parquet
  features/festivals.yaml
  models/              # baselines.py, lgbm.py, backtest.py, metrics.py, tune.py, training.py
  tracking.py          # MLflow config (DagsHub, local SQLite fallback)
  registry/promote.py  # champion/challenger gate
  predict/batch.py     # writes forecasts table
  monitor/drift.py     # Evidently reports + live accuracy
  alerts/              # channel.py (Stage-1 channel post), admin.py, revalidate.py
  bot/                 # Telegram bot: handlers, store, names, alerts (crossings + digests), moves
  api/main.py          # FastAPI app
  pipeline.py          # orchestrates steps; `--steps` CLI flag
config/series.yaml     # the modelled crop x market x variety series (editable)
config/aliases.yaml    # crop / market names people type (ml + en) for the bot
web/                   # Next.js dashboard (Vercel): app/[lang]/…, lib/queries.ts, i18n/{ml,en}.json
sql/schema.sql         # canonical DB schema
docker/                # api.Dockerfile, docker-compose.yml
tests/                 # unit, data-contract, model-quality tests
.github/workflows/     # ci.yml, daily_pipeline.yml, deploy.yml
```

## Commands

```bash
uv sync                                         # install
docker compose -f docker/docker-compose.yml up -d   # local postgres + mlflow
uv run python -m cropcast.pipeline --steps all  # daily data steps: ingest,validate,weather,clean
uv run python -m cropcast.pipeline --steps ingest,validate
uv run python -m cropcast.pipeline --steps clean --full                 # re-evaluate aliases, rebuild prices_clean
uv run python -m cropcast.pipeline --steps features,train,backtest      # Phase 2 models -> MLflow + model_metrics
uv run python -m cropcast.pipeline --steps features,train,backtest --tune   # + Optuna (h=7, folds 1-3, <=30 trials)
uv run python -m cropcast.pipeline --steps train --dry-run   # no DB / MLflow / registry writes
uv run uvicorn cropcast.api.main:app --reload   # API on :8000
cd web && npx -y pnpm@12.9.1 install && npx -y pnpm@12.9.1 dev   # dashboard on :3000 (DATABASE_URL_RO in web/.env.local)
cd web && npx -y pnpm@12.9.1 lint && npx -y pnpm@12.9.1 typecheck && npx -y pnpm@12.9.1 build
uv run pytest -q                                # tests
uv run ruff check . && uv run ruff format . && uv run mypy src
```

Run `ruff`, `mypy` and `pytest` before declaring any task done.

## Environment variables (see `.env.example`)

`DATABASE_URL`, `DATAGOV_API_KEY`, `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME`, `MLFLOW_TRACKING_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`, `ENV` (`local|ci|prod`). Phase 5: `DATABASE_URL_BOT`,
`TELEGRAM_WEBHOOK_SECRET`, `CONFIG_DIR` (API image: `/app/config`).

Also: `TEST_DATABASE_URL` (throwaway DB for tests; an autouse fixture points every test at it so tests
can never reach Neon), `LOCAL_DB_URL` (dev Postgres in `D:\pg`, see `scripts/pg_local.ps1`).
**`DATABASE_URL` in `.env` is Neon (the source of truth)** — for local dev runs override it explicitly.
Phase 4: `DATABASE_URL_RO` (read-only role `cropcast_ro`, SELECT on the 8 serving tables; created by
`scripts/setup_ro_role.py`) — the API and the dashboard use **only** this URL. `VERCEL_REVALIDATE_URL` +
`REVALIDATE_SECRET` (the `revalidate` step), `CORS_ORIGINS`.

Never hardcode secrets. Never commit `.env`. Read env only via `cropcast.config.settings`.

---

## Data rules

- **Sources (daily ingest order — `INGEST_SOURCES`, default `agmarknet,datagov`):**
  1. **Agmarknet 2.0 report API** (`api.agmarknet.gov.in/v1`) — **primary**. Any date, same naming as the
     backfill, and the daily run re-pulls the last 3 days (late market reports).
  2. **data.gov.in** "Current Daily Price of Various Commodities from Various Markets (Mandi)" — **fallback**;
     returns **today only**. Keep the resource ID in config, not code.
  - If **both** fail (error or zero rows) the run fails → `pipeline_runs.status='failed'` + Telegram admin alert.
  - Every row keeps its `source` (`agmarknet_v2`, `agmarknet` = data.gov.in, `file:<name>`).
  - Agmarknet 2.0 date-wise report — one-time historical backfill from 2018 (`scripts/backfill.py`).
  - Rubber Board daily prices for rubber; Spices Board / Kochi for pepper (Agmarknet Kerala coverage is thin for these).
  - Open-Meteo for district rainfall/temperature.
- Filter to `state == "Kerala"` at ingest. Normalize commodity/market/variety names via `ingest/mappings.py` (one canonical name per entity).
- `prices_raw` primary key is `(date, market, commodity, variety)`. **All writes are idempotent upserts** — re-running a day must never duplicate rows.
- Pandera contract (fail the pipeline, don't silently drop): `modal_price > 0` always; `min_price <= modal_price <= max_price` for the bounds that are present (min/max are **NULL** when a market reports only the modal price — published as min = max = 0, converted in `normalize()`; migration 002); no future dates, no duplicate keys. Log and quarantine bad rows to `prices_rejected`.
- **`prices_raw` is never mutated** (except the two sanctioned operations below). Recovery of quarantined rows only *inserts* (`ON CONFLICT DO NOTHING`).
- **Arrivals:** `arrivals_tonnes` (metric tonnes, nullable) is stored with every Agmarknet report (migration 004); `prices_clean` holds the day's sum. Backfilled 2018→ by exact match from cached responses (`scripts/backfill_arrivals.py`).
- **Archive (free tier):** Neon `prices_raw` keeps only the last **90 days**. Older rows are archived to GitHub Releases `data-archive-<date>` (yearly parquet; downloaded back and verified by per-year row count + modal checksum **before** delete, then `VACUUM FULL`), recorded in `archive_log` (migration 005). Monthly `archive` step (daily workflow, scheduled run on the 1st). `prices_clean` keeps the full history in the DB; `clean --full` reads archived rows back from the releases; `backfill.py` never re-inserts archived dates. The local dev DB is not archived.
- **Clean layer** (`clean` step, runs daily; migration 003):
  - `variety_aliases`: candidate renames in `ingest/variety_aliases.yaml`, accepted **per market** only if the
    raw label stops and the canonical label starts at the portal switch (>= 5 reports per side) and
    `|median(30 d before) / median(30 d after) - 1| <= 10 %`. Accepted aliases relabel rows dated before the
    switch; every decision is logged (+ `reports/alias_decisions.csv`). 19 of 98 accepted at Phase 2.
  - `prices_clean`: `prices_raw` + quarantined same-day duplicate reports, aliases applied, aggregated per
    (commodity, market, variety, date): median modal, min of min, max of max, `n_reports`, `sources`.
    Last 30 days rebuilt each run; `--full` rebuilds everything. **Models read `prices_clean`, never `prices_raw`.**
- **Portal switch:** Agmarknet 2.0 cut-over `settings.portal_switch_date = 2025-11-07` (labels changed; some
  series stopped). Feature `portal_v2` = origin on/after it.
- All SQL files are re-applied on every run (`init_db` = schema.sql + every migration), so they must be idempotent.
- Prices are ₹/quintal. Keep units consistent; convert Rubber Board (₹/kg) at ingest and document it.
- Missing market-days are normal (holidays, no arrivals). Do not forward-fill the target; forward-fill only lag features, max 3 days.

## Modeling rules

- Modelled series: `config/series.yaml` (ask before changing): the original 20 (19 from `notebooks/eda.ipynb` §9 +
  rubber Kalpetta RSS-4) + **15 Phase 6b series** (approved 2026-10-09 from a coverage report: ≥ 2 yrs, < 20 %
  missing Mon–Sat, alive): arecanut (Manjeswaram, Payyannur), coffee (Kalpetta), green ginger (Kayamkulam,
  Manjeswaram), banana Palayankodan (Kayamkulam), Poovan (Palakkad), tomato / onion big / small onion / green chilli /
  drumstick (Kayamkulam), small onion (Palakkad), bitter gourd (Manjeswaram), cucumber (Payyannur).
- **Crop (product) keys:** one commodity can hold several products, so series carry an optional `crop:`
  (`palayankodan`, `poovan` = banana varieties; `small_onion` = onion · Small; default = commodity). Dashboard
  (`web/lib/crops.ts` CROP_DEFS), bot (`config/aliases.yaml` crops, same order) and channel (`config/channel.yaml`)
  all use product keys; DB tables keep commodity / market / variety.
- **Phase 6b crops are stored for their selected markets only** (`ingest/mappings.py::selected_markets`, all varieties
  at those markets): +5 MB instead of +155 MB. The original five crops keep every Kerala market. Their 2018→ history
  lives in GitHub Release `data-archive-2026-10-09-phase6b` (36,196 rows, verified; `scripts/backfill.py
  --archive-history TAG`) and reaches `prices_clean` through `clean --full` like the main archive.
- **Excluded (recheck quarterly):** banana Robusta (best series 21.7 % missing > 20 % rule: Thalayolaparambu,
  Attingal); cardamom (40 %), dry ginger (35 %), turmeric / raw turmeric (> 75 %) are too sparse on Agmarknet —
  cardamom needs the Spices Board e-auction source (future phase).
- Training reads `prices_clean` **once** into `data/snapshots/prices_clean_<date>.parquet` (+ weather); features
  go to `data/features/*.parquet`. Never query the DB per fold; never store features in Postgres.
- Target: `log1p(modal_price)` per (market, commodity, variety). Invert with `expm1` before scoring. LightGBM
  learns the change vs `log1p(last value)` and adds it back (trees cannot extrapolate price levels).
- **Global LightGBM** across all series; `market`, `commodity`, `variety` as categorical.
- **Direct multi-horizon:** separate models for h = 1, 7, 14 days.
- Quantile models α = 0.1 / 0.5 / 0.9 → `p10/p50/p90`.
- Features (all in `features/build.py` → `build_features(prices_clean, weather, asof, horizon)`, shared by train and predict): lags 1,2,3,7,14,28; rolling mean/CV 7,28; pct change; min–max spread; n_reports; days_since_last_obs; dow/month/weekofyear; festival window flags (−14..0 d: Onam, Vishu, Christmas, Ramzan, Bakrid — `features/festivals.yaml`, 2018–2027); monsoon flag; district rain 7d/30d + temp 7d; `portal_v2`. Lag features forward-fill ≤ 3 days; the target is never filled.
- **No leakage:** rows are keyed by forecast day d (origin = d−1); every history feature uses `.shift(1)` first and inputs are truncated to `asof`. Two tests guard this (mutate data after asof; early vs late asof) — keep them passing.
- Baselines (always computed and logged, same fit/predict interface): naive (last value), seasonal-naive (most recent same-weekday value ≤ origin, i.e. = naive for h = 7, 14), 7-day moving average.
- Validation: walk-forward, expanding window, 5 folds × 14-day test windows whose targets end at the latest date. Fold cutoff c: train rows have target ≤ c, test rows have origin in [c, c+13]. **Never shuffle. Never random split.** Early stopping uses the last 28 days of each train window.
- Metrics per series / commodity × horizon: MAPE, sMAPE, MASE, p10–p90 coverage. Always log naive (and seasonal-naive) next to every LGBM number. Aggregates → `model_metrics (split='backtest')`.
- Fix seeds (`seed=42`) and log LightGBM params, feature list, series list, data date range and git SHA to MLflow on every run.
- **MLflow:** `MLFLOW_TRACKING_URI` (DagsHub) via settings; fallback local `mlflow.db` + `./mlruns`. Experiment `cropcast-backtest`; one parent run per pipeline invocation, a nested child run per horizon.
- **Phase 2 finding:** LightGBM ties but does **not** beat naive (h=7 MAPE 4.77 vs 4.71; 2-year diagnostic 5.28 vs 5.28). The quality gate test below is therefore a strict `xfail` — remove the marker once the model genuinely wins.

## Decision rule for new models / features (Phase 2.5, applies from now on)

- Yardstick: the **52-fold walk-forward diagnostic at h = 7** (14-day folds, ≈ 2 years, p50), model and naive on identical rows (`scripts/signal_hunt.py`, `cropcast.experiments.harness`).
- An approach **wins** only if it beats naive by **≥ 3 % relative MAPE AND** a **Diebold–Mariano** test (`cropcast.models.dm`: APE loss, per-date cross-series mean, Newey–West h−1, HLN correction) gives **p < 0.05** in its favour. Classification targets: macro-F1 must beat always-flat and trend persistence, plus DM p < 0.05 (pre-register the loss; a class-balanced 0/1 loss is the one consistent with macro-F1).
- Report every experiment, including failures; per-crop wins need a multiple-comparison caveat.
- **Phase 2.5 outcome** (`reports/phase2_5_signal_hunt.md`): nothing beats naive on price level — arrivals (E1), upstream TN/KA markets (E2), no-market pooling (E3), weekly means (E4b), naive/LGBM combination (E5) all tie or lose. The only signal: **direction of > 3 % moves at h = 7** (E4a classifier: macro-F1 0.52 vs 0.24 flat / 0.41 trend; significant under class-balanced DM for coconut, pepper, rubber, tapioca; strict 0/1-loss rule not met vs always-flat).
- **Phase 3 plan from that:** champion = **naive** for every crop (p50), LightGBM p10–p90 band for uncertainty; challenger = **E4a move classifier in shadow** for coconut/pepper/rubber/tapioca (alerts become user-facing only after it meets the rule live); banana = naive only; the LGBM regressor stays a registered challenger under the existing gate.

## Registry & promotion (Phase 3: "serve honestly")

- Registered models (MLflow pyfuncs on DagsHub, **aliases** only — never stages):
  - `cropcast-price-h{1,7,14}`: **champion = naive** (p50 = last observed price) with the LightGBM
    quantile p10/p90 band applied around it in log1p space; **challenger = LightGBM p50**.
  - `cropcast-move-h7`: the E4a up/down/flat classifier, alias `challenger`, **shadow only**; per-crop
    alias `champion_<crop>` only via the live check below.
- **Price gate** (`registry/promote.py`): challenger → champion only if it beats the champion by
  **≥ 3 % relative MAPE AND DM p < 0.05** (APE loss, HAC lag h−1) on the 52-fold diagnostic.
  Every decision (refresh / promote / refuse / pass / fail / insufficient data) → MLflow
  (experiment `cropcast-registry`) **and** the `promotion_log` table.
- **The pre-registered move classifier stays on its original 20 series** (`models/move.py::PREREG_SERIES`,
  `move_series`, `move_rows`): new series never enter its training rows, shadow predictions or spec hash
  (`18b80303494e1cc5`, pinned by a test). No move alerts / pre-registration for the Phase 6b crops.
- **Move challenger:** never promoted from a backtest — only by the weekly `promotion_check`
  strictly per `reports/preregistration_e4a.md` (committed alone, before any shadow prediction;
  do not edit it). Pass → alias `champion_<crop>` + admin ping. Up/down alerts additionally need
  `move_alerts_enabled: true` in `config/channel.yaml` (a human flips it).
- Batch prediction **always** loads `models:/cropcast-price-h{h}@champion` / `cropcast-move-h7@challenger`.
- **Weekly retrain** (scheduled Sunday run, step `retrain`, ~10 min): refit band + challengers,
  register new versions, move `champion` to the refreshed naive version unless the gate promotes.
  Model logging uses the client API for metrics (MLflow 3 fluent metrics after `log_model` carry a
  LoggedModel id that DagsHub rejects).

## Monitoring

- Evidently drift (`drift` step, scheduled Sundays): reference = the 90 days before, current = last 14 days.
  **Feature drift is informational** and computed only on stationary / relative features (`*_rel` lags,
  `pct_change_*`, `roll_cv_*`, `spread`, arrival ratios — `monitor/drift.py::is_stationary`); share ≥ **50 %** is
  flagged on the dashboard `/drift` and in the weekly summary (log + release notes), never alerted.
  Target drift = K-S on weekly price changes log(p_t / p_t−7). HTML → GitHub Release `reports-<date>`;
  summary → `drift_reports` (migration 007; flag, coverage and reasons in `details`).
- Live accuracy (`evaluate` step, daily): matured `forecasts` ⋈ `prices_clean` → rolling 28-day MAPE vs
  naive and p10–p90 coverage per crop × horizon; matured `shadow_predictions` → the pre-registered
  statistics (class-balanced DM vs always-flat and trend persistence, HAC lag 6, Holm across 4 crops,
  precision bar, minimum evidence) → `model_metrics (split='live')`. Only shadow rows with the current
  **spec hash** count.
- **Escalation is on performance only** (Telegram admin + GitHub issue, label `drift`; one open issue, later
  escalations comment on it), checked weekly by the `drift` step:
  1. champion live 28-day MAPE (h = 7, all crops) > 1.5× its backtest MAPE for 7 consecutive days, **or**
  2. live p10–p90 coverage (h = 7, all crops, last 28 days) outside **70–90 %** (nominal 80 %) — judged only
     once 28 days of matured forecasts exist, **or**
  3. target drift: K-S p < **0.01** on weekly price changes.
- **Why (2026-10-07):** the first report flagged 74 % of inputs with the old rule (all features, 30 %). The
  champion is naive, so input drift cannot hurt it; price levels, lags, rolling means, weather and calendar
  inputs of a seasonal series move with the season by construction, so the alert fired every week and said
  nothing about forecast quality (alert fatigue). What users feel is error and band calibration, so those
  escalate; a shift in the distribution of weekly price changes (the thing being forecast) escalates at a
  stricter p < 0.01 because ~20 series × 14 days make K-S very sensitive. Relative-feature drift stays visible.
- Any pipeline failure → `pipeline_runs.status='failed'` + Telegram ping to `TELEGRAM_ADMIN_CHAT_ID`.

## API contract (FastAPI)

Built (Phase 4, `api/main.py`; reads tables only — never loads MLflow models):
- Live: API `https://cropcast-api-21tx.onrender.com` (`/docs`), dashboard `https://kerala-crop-forecaster.vercel.app`;
  UptimeRobot keyword monitor on `/health` (`"db_ok":true`, every 10 min).
- `GET /health` (always 200 within 8 s for Render's check; `db_ok:false` + logged cause when Neon is down/slow), `/crops`, `/markets`, `/forecast?crop=&market=&horizon=1|7|14`
  (with a `stale` flag: last price > 3 days old), `/history?crop=&market=&days=90`, `/metrics` (live MAPE
  next to naive + shadow progress), `/badge/{coverage,subscribers}.json` (shields.io endpoint badges).
- Pydantic response models; 10-min TTL cache; 60 req/min/IP (slowapi); CORS GET-only for the Vercel origin.
- `docker/api.Dockerfile` (python:3.11-slim, uv, `--only-group api`, non-root, HEALTHCHECK; 186 MB; /health
  0.8 s after start at 512 MB — CI enforces < 400 MB and < 20 s). `render.yaml`: free, Singapore,
  autoDeploy off; `deploy.yml` calls `RENDER_DEPLOY_HOOK` after CI passes on main.
- `POST /telegram/webhook/{sha256(secret)[:32]}` (Phase 5): checks `X-Telegram-Bot-Api-Secret-Token` against
  `TELEGRAM_WEBHOOK_SECRET` (wrong path 404, wrong header 403), answers 200 at once and handles the update in a
  background task; exempt from the per-IP limit (all updates come from Telegram). `/badge/bot-users.json` = 30-day
  active bot users.

## Telegram bot (Stage 2, Phase 5 — `src/cropcast/bot/`, @keralacropprices_bot)

- **Webhook on the Render API** (no polling, no python-telegram-bot: plain `httpx`; fuzzy names via stdlib
  `difflib`). `scripts/set_webhook.py --generate-secret | --set --commands | --info | --delete`.
  Dedupe on `update_id` (`telegram_updates`, pruned after 7 days) — cold starts make Telegram retry.
- **Roles:** bot writes use `cropcast_bot` (`DATABASE_URL_BOT`, `scripts/setup_bot_role.py`): SELECT/INSERT/
  UPDATE/DELETE on `subscribers`, `user_alerts`, `telegram_updates`, `bot_events` only (SELECT is needed for
  UPDATE…WHERE / ON CONFLICT / RETURNING). Price / forecast reads keep using `cropcast_ro`, which sees only the
  aggregate views `bot_usage`, `bot_usage_daily` (no chat ids).
- **Commands** (Malayalam default, `/lang en|ml`): `/start`, `/price <crop> [market]`, `/markets <crop>`,
  `/alert <crop> <market> above|below <₹/kg>` (max 5), `/alerts`, `/stop <id>`, `/stopall`, `/subscribe <crop>`,
  `/unsubscribe <crop>`, `/help`, `/about`, `/deletedata`. Plain text naming a crop = `/price`. Inline keyboards
  for crop → market → threshold (±5 / ±10 % of the current price). Names in both languages + typos:
  `config/aliases.yaml` (exact → unique prefix → difflib ≥ 0.85; 0.75 matched "kannur" to "mookannur").
  Texts: `bot/texts/{ml,en}.yaml`; **every price message ends with "ഉറവിടം: Agmarknet · ഉറപ്പല്ല / not a guarantee"**.
- **Alerts are on REAL prices only** (`prices_clean`, never the model) and fire **once per crossing**:
  armed → triggered (message) → re-armed only after the price crosses back. Each alert stores the last
  observation it evaluated, so re-runs never repeat. A new alert whose condition already holds starts
  `triggered` (waits for a crossing; the reply says so).
- **Daily step `user_alerts`** (after `predict`, so digests carry today's 7-day range): alerts + personal digests
  (one per user per day, skipped on days without new prices), ≤ 25 msg/s, 429 → wait `retry_after`, 403 → user
  deactivated (`subscribers.active = false`; also on a `my_chat_member` "kicked" update; any new message
  re-activates).
- **Move alerts** ("likely to rise > 3 % this week") in digests only if `move_alerts_enabled.<crop>: true` in
  `config/channel.yaml` (default all false) **and** that crop's newest live verdict in `promotion_log` is "pass"
  (`bot/moves.py`; a flag without a pass is refused and logged — tested).
- **Privacy:** stored per chat: chat_id, language, digest crops, alerts, created / last_active timestamps; events
  hold command names only (never message text, names, usernames or phone numbers). `/deletedata` deletes the
  subscriber row (alerts cascade) and its events.
- **Rate limit:** 20 commands / chat / minute, in memory (one Render worker); one warning per window.
- **Metrics:** `bot_events` → views `bot_usage` (users active, active 7 d / 30 d, alerts active / created /
  triggered, digest users) and `bot_usage_daily`; dashboard `/health` "Bot usage"; README badge; Sunday
  `weekly_summary` step → Telegram admin (channel members, bot users, alerts, pipeline health, Neon size).
- **N users** for the CV = `SELECT count(*) FROM subscribers WHERE active` (= `bot_usage.users_active`).

---

## Code conventions

- Type hints everywhere; `mypy --strict` on `src/`.
- Pure functions for feature/model logic; I/O isolated in `ingest/`, `predict/`, and DB helpers.
- Each pipeline step is a function `run_<step>(ctx: RunContext) -> StepResult` so it can be wrapped as a Prefect `@task` later without changes.
- Use `logging` (structured, JSON in CI/prod) — no `print`.
- External HTTP: `httpx` with timeouts + `tenacity` retries (3×, exponential backoff).
- SQL changes go in `sql/schema.sql` and a numbered migration in `sql/migrations/`.
- Small, focused commits. Conventional commit messages (`feat:`, `fix:`, `chore:`).

## Tests that must exist and pass

- Pandera contract tests on fixture data.
- Feature leakage test (features at `t` unchanged when data after `t` is mutated).
- Idempotent ingest test (running same day twice → same row count).
- Model quality test: on frozen sample `tests/fixtures/sample_prices.parquet`, LightGBM h=7 MAPE < naive MAPE (currently `xfail(strict=True)` — see Phase 2 finding).
- Clean layer: same-day aggregation, alias guard (accept within 10 %, reject outside / two products / thin data).
- Backtest folds never overlap train/test.
- API tests with `TestClient` against a seeded test DB.

## CI/CD

- `ci.yml` (PR + main): ruff, mypy, pytest; docker build + size/cold-start check; `web` job (node LTS, pnpm: lint, typecheck, build — no DB, pages build empty and fill via ISR).
- `daily_pipeline.yml`: cron `17 14 * * *` (UTC = 19:47 IST; off the hour because GitHub delays on-the-hour crons) + `workflow_dispatch`; uploads `reports/` artifact. Steps: `ingest,validate,weather,clean,predict,user_alerts,shadow,evaluate,notify,revalidate`; scheduled Sundays add `retrain` (after clean), `promotion_check,drift` (after evaluate) and `weekly_summary` (last); the 1st adds `archive`. Full git history (`fetch-depth: 0`) — the shadow step verifies the pre-registration commit.
- `deploy.yml`: after `ci` succeeds on main → POST `RENDER_DEPLOY_HOOK` (Render builds the image). The dashboard deploys via the Vercel GitHub integration (root `web/`).

## Don'ts

- Don't random-split or shuffle time series.
- Don't compute features differently in training vs prediction — import from `features/build.py` only.
- Don't report a metric without the naive baseline next to it.
- Don't add new infra (Kafka, Airflow, k8s, feature stores) — free-tier and simple is the point.
- Don't scrape sites aggressively; respect rate limits, cache responses in `data/cache/`.
- Don't touch `data/raw/` files after ingest — they're immutable.

## Dashboard design system (Phase 6a, `web/`)

- **Farmer-first:** home = crop cards (lead-market price, ▲/▼ vs 7 days, server-SVG sparkline, best market
  today); `/crop/<crop>[/<market>]` = price history (90d/1y/5y + forecast band), "is this price high?"
  (this year / last year / 5-yr weekly mean + month percentile), sortable market table, district map,
  Telegram alert deep link (`?start=alert_<crop>_<market-slug>`, handled in `bot/names.py`), WhatsApp
  share, per-crop OG card. Nav: Home · Crops · Alerts · How it works (evidence pages live under it).
  Old `/p/<crop>/<market>` URLs redirect.
- **Liquid-Glass-inspired, original** (no Apple fonts, symbols, logos). Tokens in `app/globals.css`
  (`@theme`): glass levels thin/regular/thick, radii, motion; light and dark designed separately.
  Components: `components/glass.tsx` (GlassCard, DataCard, Chip, PriceBadge, TrendPill), `Chrome`
  (nav + tab bar), `Sheet` (`<dialog>`), `MiniSpark`/`Sparkline` (server SVG), `KeralaMap`, `MarketTable`,
  `HistoryPanel`, `Charts` (Recharts).
- **Glass guardrails (mandatory):** `backdrop-filter` only on chrome (top bar, tab bar, open sheet: ≤ 3
  layers); cards use non-blurred `surface-glass`; numbers / charts / tables on near-opaque `surface-data`;
  fallbacks for `@supports not (backdrop-filter)`, `prefers-reduced-transparency`, `prefers-contrast: more`,
  `prefers-reduced-motion`. Chrome over scrolling content uses the thick level (scrim) so text stays ≥ 4.5:1.
- **Performance:** no Recharts before the first user interaction (server SVG stand-ins show the data);
  one font preload (Noto Sans Malayalam, Malayalam subset; Latin = system UI font); no link prefetch on
  long lists. Budget: Lighthouse mobile ≥ 90, accessibility 100, CLS 0 (`npm run test:e2e` + 3 Lighthouse
  runs, median).
- **Charts** follow the dataviz method: slots blue / orange / aqua (validated all-pairs, light + dark),
  sequential blue for the map, legend + direct labels, table view for the seasonal chart.
- **OG images with Malayalam:** Satori cannot shape Indic scripts, so fixed Malayalam phrases are
  pre-shaped offline with HarfBuzz (Noto Sans Malayalam Bold, OFL) into SVG paths (`lib/og-glyphs.ts`);
  add a phrase by re-running the generator, never by typing Malayalam into `ImageResponse`.
- **Map:** `lib/kerala-map.ts`, generated once from geoBoundaries IND ADM2 (ODbL 1.0, attribution under the
  map); market → district from `prices_raw`.
- **Env (Vercel, Production + Preview) is exactly:** `DATABASE_URL_RO`, `REVALIDATE_SECRET`,
  `NEXT_PUBLIC_TELEGRAM_CHANNEL_URL`. Never add pipeline / bot / MLflow secrets to Vercel. Platform-provided:
  `VERCEL_PROJECT_PRODUCTION_URL`, `NODE_ENV`. Test-only: `BASE_URL`, `PW_CHANNEL`, `SHOTS_DIR`,
  `VERCEL_AUTOMATION_BYPASS_SECRET` (local `.env`; Playwright / Lighthouse send it as
  `x-vercel-protection-bypass` to reach protected previews). Preview Lighthouse runs block the Vercel
  toolbar (`--blocked-url-patterns=*vercel.live*`): it is injected on previews only.
- **PWA:** `app/manifest.ts`, `public/icons/*`, `public/sw.js` (network-first pages with cache fallback, then
  `/offline`; cache-first hashed static assets), install prompt (Android) / hint (iOS).

## Free-tier constraints

The project must cost **₹0** to run. Every design choice has to fit these free tiers:

| Service | Use | Limit to respect |
|---|---|---|
| GitHub Actions | CI + daily cron | Repo stays **public** (unlimited minutes). Scheduled workflows are disabled after 60 days without repo activity → the daily job commits `status/last_run.json`. |
| Neon Postgres | source of truth | **0.5 GB** storage → keep the DB **< 400 MB** (196 MB after Phase 1; 304 MB after Phase 2; **137 MB** after the Phase 2.5 archive — `prices_clean` 111 MB of it; `prices_raw` 90 days only). |
| DagsHub | MLflow tracking + registry | Public repo; keep artifacts small (models, not datasets). |
| Render | FastAPI + Telegram webhook | Free web service sleeps after idle; cold starts are fine for batch-serving. **No Render Postgres** (expires) — Neon only. |
| Vercel (Hobby) | Next.js dashboard | **Non-commercial only**; 100 GB bandwidth/month, 100k function invocations/month, **10 s** function limit → pages are ISR (`revalidate = 3600`) + on-demand revalidation after the daily run, so almost every view is a static hit; every query must finish well under 10 s (all < 1 s, indexed). Reads Neon via `DATABASE_URL_RO`, server-side only. |

Rules:
- **DB budget:** < 400 MB total. Log `db_size_mb` on every pipeline run (`pipeline_runs.details`) and fail loudly / ping admin before the limit, not after.
- **Features go to parquet** (artifacts / `data/`), never into Postgres tables.
- **Retention:** `forecasts` and `shadow_predictions` older than **180 days**, `prices_raw` older than
  **90 days** → monthly `archive` step → verified GitHub Release → deleted from Neon (live-accuracy
  history stays in `model_metrics`, which is small).
- **Read-only serving:** API and dashboard connect as `cropcast_ro` (SELECT only); never give them `DATABASE_URL`.
- **Dashboard revalidation:** the `revalidate` step POSTs `VERCEL_REVALIDATE_URL` with header `x-revalidate-secret`;
  a failure is a warning (the hourly ISR window self-heals), never a failed run.
- Don't store raw API payloads in Postgres; they live in `data/cache/` and the run artifact.
- **Telegram webhook:** dedupe on `update_id` (Telegram retries when a cold-starting Render instance is slow) so a retried update is never processed twice.

## Telegram rollout (staged)

- **Stage 1 — Phase 3 (built):** **one** public channel (all crops in one post; per-crop channels later).
  The `notify` step posts once per day after a successful run: per crop ONE market (Phase 6b: 17 crops, kept
  short; `config/channel.yaml`) with the latest modal price (₹/kg = Agmarknet ₹/quintal ÷ 100; dated if not
  today's) and the champion's p10–p90 for the price 7 days ahead; Malayalam line first, English second
  (`alerts/templates/{ml,en}.yaml`); footer: source, "range, not a guarantee", repo link. **No move
  alerts** until the classifier is promoted and the flag is on. Idempotent (`channel_posts`), skipped
  when nothing new was ingested today (IST), member count → `channel_stats`. Needs secrets
  `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHANNEL_ID`; without them (and in CI / `--dry-run`) the post is logged,
  not sent.
- **Stage 2 — Phase 5 (built):** the interactive bot @keralacropprices_bot on the Render webhook — see
  "Telegram bot". The channel post is unchanged.

## Build order / status

- [x] 1. Daily ingest cron live (start early — history accumulates) + backfill + EDA
      (daily source order: Agmarknet 2.0 report API → data.gov.in fallback; Rubber Board stubbed;
      backfill 2018-01→ via Agmarknet 2.0; recommended series in `notebooks/eda.ipynb` §9)
- [x] 2. Baselines, features, LightGBM, walk-forward backtest, MLflow logging
      (clean layer + aliases + nullable min/max; 19 series in `config/series.yaml`; report in
      `notebooks/02_backtest_report.ipynb`; LGBM ties naive — quality gate is a strict xfail)
- [x] 2.5 Signal hunt (time-boxed): arrivals stored, prices_raw archive to GitHub Releases, E0–E5 vs the
      decision rule — no price model beats naive; E4a direction classifier is the Phase 3 shadow challenger
- [x] 3. Registry + promotion gate + batch predict → Postgres ("serve honestly": naive champion + LGBM band,
      shadow move classifier under `reports/preregistration_e4a.md`, Telegram Stage 1 channel post, retention)
- [x] 4. Serve + observe: read-only role, FastAPI on Render (Docker), Next.js dashboard on Vercel (ISR +
      revalidate step), weekly Evidently drift + escalation, README overhaul (Streamlit replaced by Vercel).
      Live since 2026-10-08: API https://cropcast-api-21tx.onrender.com, dashboard
      https://kerala-crop-forecaster.vercel.app, Telegram https://t.me/keralavipanivila.
      Lighthouse mobile on live `/` (2026-10-08, 5 runs): performance 91–95 (median 94), accessibility,
      best practices, SEO 100 — charts load only after first paint + idle; font `display: optional`.
      Revalidate step verified live (status ok). Open: `RENDER_DEPLOY_HOOK` secret must be the full hook URL
      (deploy.yml validates it); until then Render deploys are manual.
- [ ] 5. Telegram bot (Stage 2): built 2026-10-09 (webhook, commands ml/en, crossing alerts, digests, roles,
      metrics, tests); tick once it answers on Render and a daily run has fired a real alert
- [ ] 6. CI/CD polish, README (diagram, live MAPE badge), user acquisition
  - [x] 6a. Frontend upgrade (farmer-first, Liquid-Glass-inspired, PWA), PR #3, live 2026-10-09.
        Production Lighthouse mobile (median of 3): home 95, crop pages 91 / 93; a11y 100; CLS 0;
        Playwright + axe 20/20 on production

Update this checklist as phases complete.
