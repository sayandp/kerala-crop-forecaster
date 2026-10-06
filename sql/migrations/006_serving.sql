-- Migration 006 (Phase 3, "serve honestly"): forecasts keyed by series, shadow predictions,
-- promotion log, Telegram channel bookkeeping, archive_log per table. Idempotent.

-- forecasts: series are (commodity, market, variety); record model + the price it started from.
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS variety     TEXT;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS model_name  TEXT;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS last_value  NUMERIC(12, 2);
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.key_column_usage
        WHERE table_name = 'forecasts' AND constraint_name = 'forecasts_pkey'
          AND column_name = 'variety'
    ) THEN
        ALTER TABLE forecasts DROP CONSTRAINT IF EXISTS forecasts_pkey;
        UPDATE forecasts SET variety = '' WHERE variety IS NULL;
        ALTER TABLE forecasts ALTER COLUMN variety SET NOT NULL;
        ALTER TABLE forecasts ADD PRIMARY KEY (forecast_date, horizon, commodity, market, variety);
    END IF;
END $$;

-- Shadow (never user-facing) predictions of the move challenger (preregistration_e4a.md).
CREATE TABLE IF NOT EXISTS shadow_predictions (
    forecast_date  DATE           NOT NULL,   -- origin: last data day used
    target_date    DATE           NOT NULL,   -- forecast_date + 7
    commodity      TEXT           NOT NULL,
    market         TEXT           NOT NULL,
    variety        TEXT           NOT NULL,
    pred_class     TEXT           NOT NULL CHECK (pred_class IN ('down', 'flat', 'up')),
    p_down         DOUBLE PRECISION NOT NULL,
    p_flat         DOUBLE PRECISION NOT NULL,
    p_up           DOUBLE PRECISION NOT NULL,
    trend_class    TEXT           NOT NULL CHECK (trend_class IN ('down', 'flat', 'up')),
    last_value     NUMERIC(12, 2) NOT NULL,
    model_version  TEXT           NOT NULL,
    spec_hash      TEXT           NOT NULL,
    prereg_commit  TEXT           NOT NULL,   -- commit of reports/preregistration_e4a.md
    run_id         BIGINT,
    created_at     TIMESTAMPTZ    NOT NULL DEFAULT now(),
    PRIMARY KEY (forecast_date, commodity, market, variety)
);

-- Every registry gate decision (price gate, champion refresh, live move-model verdicts).
CREATE TABLE IF NOT EXISTS promotion_log (
    id                  BIGSERIAL   PRIMARY KEY,
    decided_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_name          TEXT        NOT NULL,
    scope               TEXT        NOT NULL,   -- 'all' or a crop
    challenger_version  TEXT,
    champion_version    TEXT,
    decision            TEXT        NOT NULL,   -- promote | refuse | refresh | pass | fail | insufficient data
    reason              TEXT        NOT NULL,
    metrics             JSONB,
    mlflow_run_id       TEXT,
    run_id              BIGINT
);

-- Telegram Stage 1: one post per date (idempotency) and daily subscriber counts.
CREATE TABLE IF NOT EXISTS channel_posts (
    post_date   DATE        PRIMARY KEY,
    chat_id     TEXT        NOT NULL,
    message_id  BIGINT,
    text        TEXT        NOT NULL,
    posted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS channel_stats (
    date          DATE        PRIMARY KEY,
    member_count  INTEGER     NOT NULL,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- archive_log now covers several tables (prices_raw, forecasts, shadow_predictions).
ALTER TABLE archive_log ADD COLUMN IF NOT EXISTS table_name TEXT NOT NULL DEFAULT 'prices_raw';
