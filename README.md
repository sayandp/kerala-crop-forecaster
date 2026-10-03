# cropcast — Kerala Crop Price Forecaster

Self-retraining MLOps system that forecasts daily mandi prices for Kerala crops
(banana/Nendran, coconut, rubber RSS-4, pepper, tapioca). See `CLAUDE.md` for the
full design. Currently at **Phase 1**: daily ingest + historical backfill + EDA.

## Quickstart

```bash
uv sync
cp .env.example .env            # fill in secrets
docker compose -f docker/docker-compose.yml up -d
uv run python -m cropcast.pipeline --steps ingest,validate
uv run python scripts/backfill.py --start 2018-01 --end 2026-09
```
