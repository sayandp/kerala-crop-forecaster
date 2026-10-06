# CLAUDE.md — Kerala Crop Price Forecaster

Self-retraining MLOps system that forecasts daily mandi (modal) prices for Kerala crops — banana (Nendran), coconut, rubber (RSS-4), pepper, tapioca — and pushes price alerts to farmers/traders via Telegram.

**Goal of the project:** a production-grade, end-to-end MLOps portfolio piece with real users. Every design choice should favour reliability, reproducibility and honest metrics over cleverness.

---

## Architecture (one-line summary)

GitHub Actions cron (daily 19:47 IST) → ingest → validate → features → train challenger → backtest vs baselines → promotion gate (MLflow registry) → batch predict with `@champion` → Postgres → served by FastAPI / Streamlit / Telegram bot. Evidently monitors drift; live MAPE is computed as actuals arrive.

**Serving is batch, not real-time.** Forecasts are precomputed nightly and read from Postgres. Do not add online inference.

## Stack

- Python 3.11, `uv` for deps (`pyproject.toml` + `uv.lock`)
- pandas, numpy, LightGBM, scikit-learn, Pandera
- MLflow (tracking + model registry, hosted on DagsHub)
- Postgres (Neon/Supabase in prod, docker-compose locally), SQLAlchemy 2.x + psycopg
- FastAPI + Uvicorn, Streamlit, python-telegram-bot (webhook mode inside FastAPI)
- Evidently (drift reports)
- GitHub Actions (CI, daily pipeline, deploy); Prefect-compatible task/flow structure
- Docker, ruff, mypy, pytest

## Repo layout

```
src/cropcast/
  config.py            # pydantic-settings; ALL env vars read here only
  ingest/              # agmarknet.py, rubberboard.py, weather.py
  validate/schemas.py  # Pandera schemas (data contracts)
  features/build.py    # feature engineering — single source of truth
  models/              # baselines.py, lgbm.py, backtest.py
  registry/promote.py  # champion/challenger gate
  predict/batch.py     # writes forecasts table
  monitor/drift.py     # Evidently reports + live accuracy
  alerts/telegram_bot.py
  api/main.py          # FastAPI app
  pipeline.py          # orchestrates steps; `--steps` CLI flag
dashboard/app.py       # Streamlit
sql/schema.sql         # canonical DB schema
docker/                # api.Dockerfile, docker-compose.yml
tests/                 # unit, data-contract, model-quality tests
.github/workflows/     # ci.yml, daily_pipeline.yml, deploy.yml
```

## Commands

```bash
uv sync                                         # install
docker compose -f docker/docker-compose.yml up -d   # local postgres + mlflow
uv run python -m cropcast.pipeline --steps all  # full daily pipeline
uv run python -m cropcast.pipeline --steps ingest,validate
uv run python -m cropcast.pipeline --steps train --dry-run   # no registry writes
uv run uvicorn cropcast.api.main:app --reload   # API on :8000
uv run streamlit run dashboard/app.py           # dashboard on :8501
uv run pytest -q                                # tests
uv run ruff check . && uv run ruff format . && uv run mypy src
```

Run `ruff`, `mypy` and `pytest` before declaring any task done.

## Environment variables (see `.env.example`)

`DATABASE_URL`, `DATAGOV_API_KEY`, `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME`, `MLFLOW_TRACKING_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`, `ENV` (`local|ci|prod`).

Never hardcode secrets. Never commit `.env`. Read env only via `cropcast.config.settings`.

---

## Data rules

- **Sources:**
  - data.gov.in "Current Daily Price of Various Commodities from Various Markets (Mandi)" API — returns **today only**; history is built by the daily pull. Keep the resource ID in config, not code.
  - Agmarknet portal reports — one-time historical backfill (`scripts/backfill.py`).
  - Rubber Board daily prices for rubber; Spices Board / Kochi for pepper (Agmarknet Kerala coverage is thin for these).
  - Open-Meteo for district rainfall/temperature.
- Filter to `state == "Kerala"` at ingest. Normalize commodity/market/variety names via `ingest/mappings.py` (one canonical name per entity).
- `prices_raw` primary key is `(date, market, commodity, variety)`. **All writes are idempotent upserts** — re-running a day must never duplicate rows.
- Pandera contract (fail the pipeline, don't silently drop): `modal_price > 0`, `min_price <= modal_price <= max_price`, no future dates, no duplicate keys. Log and quarantine bad rows to `prices_rejected`.
- Prices are ₹/quintal. Keep units consistent; convert Rubber Board (₹/kg) at ingest and document it.
- Missing market-days are normal (holidays, no arrivals). Do not forward-fill the target; forward-fill only lag features, max 3 days.

## Modeling rules

- Target: `log1p(modal_price)` per (market, commodity). Invert with `expm1` before scoring.
- **Global LightGBM** across all series; `market`, `commodity` as categorical.
- **Direct multi-horizon:** separate models for h = 1, 7, 14 days.
- Quantile models α = 0.1 / 0.5 / 0.9 → `p10/p50/p90`.
- Features (all in `features/build.py`, shared by train and predict): lags 1,2,3,7,14,28; rolling mean/std 7,28; pct change; min–max spread; dow/month/weekofyear; festival flags (Onam, Vishu, Christmas, Ramzan — from `features/festivals.yaml`); monsoon flag; rainfall 7d/30d.
- **No leakage:** every feature for target date `t+h` uses only data ≤ `t`. Rolling windows must `shift(1)` first. There is a test for this — keep it passing.
- Baselines (always computed and logged): naive (last value), seasonal-naive (t−7), 7-day moving average.
- Validation: walk-forward, expanding window, 5 folds × 14-day test windows. **Never shuffle. Never random split.**
- Metrics per commodity × horizon: MAPE, sMAPE, MASE. Always log `naive_mape` alongside.
- Fix seeds (`seed=42`) and log LightGBM params, feature list, data date range and git SHA to MLflow on every run.

## Registry & promotion

- Registered model name: `cropcast-lgbm-h{horizon}`.
- Use MLflow **aliases** (`champion`, `challenger`), not deprecated stages.
- Promote challenger → champion only if: beats naive MAPE **and** ≤ champion MAPE × 1.02. Otherwise tag as `challenger`.
- Batch prediction **always** loads `models:/cropcast-lgbm-h{h}@champion`. Never predict with an unpromoted model.
- First run (no champion): promote if it beats naive.

## Monitoring

- Evidently data-drift: reference = last 90 days of training data, current = last 14 days. Save HTML to `reports/` and summary metrics to DB.
- Live accuracy: each run joins past `forecasts` with new actuals → `model_metrics (split='live')`.
- Escalation: drift on >30% of features **or** live MAPE > 1.5× backtest for 7 consecutive days → force retrain with longer window + Telegram ping to admin.
- Any pipeline failure → `pipeline_runs.status='failed'` + Telegram ping to `TELEGRAM_ADMIN_CHAT_ID`.

## API contract (FastAPI)

- `GET /forecast?commodity=&market=&horizon=` → `{p10, p50, p90, target_date, model_version}`
- `GET /history?commodity=&market=&days=90`
- `GET /markets`, `GET /commodities`
- `GET /metrics` → live MAPE vs naive (powers README badge)
- `GET /health` → DB ok + last successful run date
- `POST /telegram/webhook`
- Pydantic response models for everything. Read-only DB user for the API.

## Telegram bot

- Commands: `/start`, `/subscribe <crop> <market>`, `/price <crop>`, `/unsubscribe`, `/lang ml|en`.
- Default language **Malayalam** (`lang='ml'`); templates in `alerts/templates/{ml,en}.yaml`.
- Alert only when forecast move ≥ subscriber `threshold_pct` (default 5%). Max 1 alert per subscriber per day.
- Active user count = `SELECT count(*) FROM subscribers WHERE active` — this is the CV "N users" number.

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
- Model quality test: on frozen sample `tests/fixtures/sample_prices.parquet`, LightGBM h=7 MAPE < naive MAPE.
- API tests with `TestClient` against a seeded test DB.

## CI/CD

- `ci.yml` (PR): ruff, mypy, pytest, docker build.
- `daily_pipeline.yml`: cron `17 14 * * *` (UTC = 19:47 IST; off the hour because GitHub delays on-the-hour crons) + `workflow_dispatch`; uploads `reports/` artifact.
- `deploy.yml` (push to main): build → push GHCR → Render deploy hook.

## Don'ts

- Don't random-split or shuffle time series.
- Don't compute features differently in training vs prediction — import from `features/build.py` only.
- Don't report a metric without the naive baseline next to it.
- Don't add new infra (Kafka, Airflow, k8s, feature stores) — free-tier and simple is the point.
- Don't scrape sites aggressively; respect rate limits, cache responses in `data/cache/`.
- Don't touch `data/raw/` files after ingest — they're immutable.

## Free-tier constraints

The project must cost **₹0** to run. Every design choice has to fit these free tiers:

| Service | Use | Limit to respect |
|---|---|---|
| GitHub Actions | CI + daily cron | Repo stays **public** (unlimited minutes). Scheduled workflows are disabled after 60 days without repo activity → the daily job commits `status/last_run.json`. |
| Neon Postgres | source of truth | **0.5 GB** storage → keep the DB **< 400 MB** (196 MB after Phase 1 backfill). |
| DagsHub | MLflow tracking + registry | Public repo; keep artifacts small (models, not datasets). |
| Render | FastAPI + Telegram webhook | Free web service sleeps after idle; cold starts are fine for batch-serving. **No Render Postgres** (expires) — Neon only. |
| Streamlit Community Cloud | dashboard | Public app, reads Neon via the read-only user. |

Rules:
- **DB budget:** < 400 MB total. Log `db_size_mb` on every pipeline run (`pipeline_runs.details`) and fail loudly / ping admin before the limit, not after.
- **Features go to parquet** (artifacts / `data/`), never into Postgres tables.
- **Prune `forecasts` older than 180 days** (live-accuracy history lives in `model_metrics`, which is small).
- Don't store raw API payloads in Postgres; they live in `data/cache/` and the run artifact.
- **Telegram webhook:** dedupe on `update_id` (Telegram retries when a cold-starting Render instance is slow) so a retried update is never processed twice.

## Telegram rollout (staged)

- **Stage 1 — end of Phase 3:** one public Telegram **channel per crop**; the daily job posts the
  forecast summary after batch predict (plain Bot API `sendMessage`, no webhook, no subscribers table).
- **Stage 2 — Phase 5:** the interactive bot (`/subscribe`, `/price`, `/lang`, threshold alerts) via
  the Render webhook described under "Telegram bot".

## Build order / status

- [x] 1. Daily ingest cron live (start early — history accumulates) + backfill + EDA
      (daily source order: Agmarknet 2.0 report API → data.gov.in fallback; Rubber Board stubbed;
      backfill 2018-01→ via Agmarknet 2.0; recommended series in `notebooks/eda.ipynb` §9)
- [ ] 2. Baselines, features, LightGBM, walk-forward backtest, MLflow logging
- [ ] 3. Registry + promotion gate + batch predict → Postgres
- [ ] 4. FastAPI + Docker + deploy; Streamlit dashboard
- [ ] 5. Evidently drift + live accuracy + Telegram bot
- [ ] 6. CI/CD polish, README (diagram, live MAPE badge), user acquisition

Update this checklist as phases complete.
