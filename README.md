# cropcast — Kerala Crop Price Forecaster

Self-retraining MLOps system that forecasts daily mandi prices for Kerala crops
(banana/Nendran, coconut, rubber RSS-4, pepper, tapioca). See `CLAUDE.md` for the
full design. **Status: Phase 2 done** — daily ingest + clean layer, features, LightGBM vs baselines
backtest logged to MLflow (DagsHub). Report: `notebooks/02_backtest_report.ipynb`.

## Quickstart

```bash
uv sync
cp .env.example .env                                   # fill in secrets
docker compose -f docker/docker-compose.yml up -d      # or: .\scripts\pg_local.ps1 start
uv run python -m cropcast.pipeline --steps ingest,validate,weather
uv run python scripts/backfill.py --start 2018-01 --weather   # one-time, ~40 min, resumable
uv run pytest -q
```

## Databases

**Neon is the source of truth** (the `DATABASE_URL` GitHub secret; the daily job writes there).
The local Postgres is for development only — never treat it as authoritative.

Local dev Postgres 16 lives in `D:\pg` (portable binaries + data dir, outside Temp so
Windows cleanup can't touch it):

```powershell
.\scripts\pg_local.ps1 start | stop | restart | status | check   # check = row counts
```

`scripts/copy_to_neon.py` was the one-time local → Neon migration.

## Data sources

| Data | Source | Notes |
|---|---|---|
| Daily mandi prices (primary) | Agmarknet 2.0 report API `api.agmarknet.gov.in/v1` — *Commodity-wise, Market-wise Daily Report for State* | Any date; the daily run re-pulls the last 3 days to catch late market reports. |
| Daily mandi prices (fallback) | data.gov.in resource `9ef84268-d588-465a-a308-a864a43d0070` | Today only; needs `DATAGOV_API_KEY`. |
| History 2018→ | Agmarknet 2.0 *Date-wise Prices for Specified Commodity* (per crop × month) | `scripts/backfill.py`; cached + checkpointed. |
| Weather | Open-Meteo archive + forecast APIs | District HQ coordinates in `src/cropcast/ingest/districts.yaml`. |
| Rubber Board | — | Not implemented: no stable public endpoint (see `ingest/rubberboard.py`). Rubber RSS-4 comes from Agmarknet. |

All prices are **Rs./quintal**. Non-quintal rows (e.g. Rs./bundle leafy greens) are skipped.
Requests are rate-limited (2 s between calls per host), retried 3× with exponential
backoff, and raw responses are cached in `data/cache/`.

## Pipeline

```
python -m cropcast.pipeline --steps ingest,validate,weather [--date YYYY-MM-DD] [--lookback 3] [--dry-run]
```

* **ingest** — fetch → `normalize()` (canonical names, `ingest/mappings.py`) → immutable
  parquet snapshot in `data/raw/prices/run_date=…/`.
* **validate** — Pandera contract (`validate/schemas.py`); failing rows go to
  `prices_rejected` with a reason; the run fails if > 20 % are rejected; good rows are
  upserted into `prices_raw` (idempotent on `(date, market, commodity, variety)`).
* **weather** — district rainfall/temperature → `weather_daily`.

Every run is logged in `pipeline_runs`; a failure pings `TELEGRAM_ADMIN_CHAT_ID`.

### Backfill from your own file

`scripts/backfill.py --input FILE` accepts `.csv` or `.parquet` with one row per
(date, market, commodity, variety):

| column | required | format |
|---|---|---|
| `date` (or `arrival_date`) | yes | `yyyy-mm-dd` or `dd/mm/yyyy` |
| `market`, `commodity`, `variety` | yes | raw Agmarknet names are fine (normalized on load) |
| `min_price`, `max_price`, `modal_price` | yes | Rs./quintal |
| `state` | no | if present, only Kerala/Keralam rows are kept |
| `district` | no | filled from the market lookup when missing |

Column names are case-insensitive; data.gov.in style keys (`Modal_x0020_Price`) also work.

## GitHub secrets

| Secret | Used by | Required |
|---|---|---|
| `DATABASE_URL` | daily pipeline | yes — e.g. Neon `postgresql+psycopg://user:pass@host/db?sslmode=require` |
| `TELEGRAM_BOT_TOKEN` | failure pings | recommended |
| `TELEGRAM_ADMIN_CHAT_ID` | failure pings | recommended |
| `DATAGOV_API_KEY` | data.gov.in fallback | optional |
