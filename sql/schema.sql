-- Canonical database schema for cropcast.
-- Every change here must also land as a numbered migration in sql/migrations/.
-- init_db() applies this file and then every migration in order on every run, so all
-- statements (here and in migrations) MUST be idempotent (IF NOT EXISTS, DROP NOT NULL, ...).
-- Units: all prices are Rs./quintal. Rubber Board Rs./kg prices are converted (x100) at ingest.

-- ---------------------------------------------------------------------------
-- Raw daily mandi prices (idempotent upserts on the natural key)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prices_raw (
    date         DATE           NOT NULL,
    state        TEXT           NOT NULL,
    district     TEXT,
    market       TEXT           NOT NULL,
    commodity    TEXT           NOT NULL,
    variety      TEXT           NOT NULL,
    min_price    NUMERIC(12, 2),            -- NULL: market reported only the modal price
    max_price    NUMERIC(12, 2),            -- NULL: market reported only the modal price
    modal_price  NUMERIC(12, 2) NOT NULL,
    arrivals_tonnes NUMERIC(12, 3),         -- arrival quantity, metric tonnes (NULL: not reported)
    source       TEXT           NOT NULL,
    ingested_at  TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ    NOT NULL DEFAULT now(),
    PRIMARY KEY (date, market, commodity, variety),
    CHECK (modal_price > 0),
    -- NULL-tolerant: a bound is only checked when it is present.
    CHECK (min_price <= modal_price AND modal_price <= max_price)
);
CREATE INDEX IF NOT EXISTS ix_prices_raw_series ON prices_raw (commodity, market, date);

-- ---------------------------------------------------------------------------
-- Clean layer (derived from prices_raw; see migration 003)
-- ---------------------------------------------------------------------------
-- Accepted variety renames (e.g. labels changed at the Agmarknet 2.0 cut-over).
-- Seeded from src/cropcast/ingest/variety_aliases.yaml; a candidate is stored only if it
-- passed the price-continuity guard for that market. market NULL = applies to all markets.
CREATE TABLE IF NOT EXISTS variety_aliases (
    id                 BIGSERIAL     PRIMARY KEY,
    commodity          TEXT          NOT NULL,
    market             TEXT,
    raw_variety        TEXT          NOT NULL,
    canonical_variety  TEXT          NOT NULL,
    valid_from         DATE,                    -- NULL = open start
    valid_to           DATE,                    -- NULL = open end (inclusive bound)
    guard_ratio        DOUBLE PRECISION,        -- median(before)/median(after) - 1
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
    UNIQUE (commodity, market, raw_variety, valid_from, valid_to)
);

-- One row per series-day: aliases applied, same-day duplicate reports aggregated
-- (median modal, min of min, max of max). Rebuilt for the last N days each run.
CREATE TABLE IF NOT EXISTS prices_clean (
    commodity    TEXT           NOT NULL,
    market       TEXT           NOT NULL,
    variety      TEXT           NOT NULL,
    date         DATE           NOT NULL,
    modal_price  NUMERIC(12, 2) NOT NULL CHECK (modal_price > 0),
    min_price    NUMERIC(12, 2),
    max_price    NUMERIC(12, 2),
    n_reports    SMALLINT       NOT NULL CHECK (n_reports >= 1),
    arrivals_tonnes NUMERIC(12, 3),         -- sum over the day's reports (NULL: none reported)
    sources      TEXT           NOT NULL,
    PRIMARY KEY (commodity, market, variety, date)
);

-- ---------------------------------------------------------------------------
-- Archive of old prices_raw rows (GitHub Release assets; see migration 005)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS archive_log (
    release_tag  TEXT        PRIMARY KEY,   -- GitHub Release, e.g. data-archive-2026-10-07
    cutoff_date  DATE        NOT NULL,      -- rows dated < cutoff_date were archived
    rows         INTEGER     NOT NULL,
    archived_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    table_name   TEXT        NOT NULL DEFAULT 'prices_raw'
);

-- ---------------------------------------------------------------------------
-- Quarantined rows that failed the data contract
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prices_rejected (
    id           BIGSERIAL      PRIMARY KEY,
    run_id       BIGINT,
    date         DATE,
    state        TEXT,
    district     TEXT,
    market       TEXT,
    commodity    TEXT,
    variety      TEXT,
    min_price    NUMERIC(12, 2),
    max_price    NUMERIC(12, 2),
    modal_price  NUMERIC(12, 2),
    arrivals_tonnes NUMERIC(12, 3),
    source       TEXT,
    reason       TEXT           NOT NULL,
    rejected_at  TIMESTAMPTZ    NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_prices_rejected_date ON prices_rejected (date);

-- ---------------------------------------------------------------------------
-- Pipeline run log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id       BIGSERIAL      PRIMARY KEY,
    run_date     DATE           NOT NULL,
    steps        TEXT           NOT NULL,
    dry_run      BOOLEAN        NOT NULL DEFAULT FALSE,
    status       TEXT           NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    started_at   TIMESTAMPTZ    NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    git_sha      TEXT,
    error        TEXT,
    details      JSONB
);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_status ON pipeline_runs (status, run_date);

-- ---------------------------------------------------------------------------
-- District daily weather (Open-Meteo)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weather_daily (
    date          DATE          NOT NULL,
    district      TEXT          NOT NULL,
    rainfall_mm   NUMERIC(8, 2),
    temp_max_c    NUMERIC(5, 2),
    temp_min_c    NUMERIC(5, 2),
    temp_mean_c   NUMERIC(5, 2),
    source        TEXT          NOT NULL DEFAULT 'open-meteo',
    ingested_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (date, district)
);

-- ---------------------------------------------------------------------------
-- Later phases (defined now so the schema is complete; unused in Phase 1)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecasts (
    run_id         BIGINT         REFERENCES pipeline_runs (run_id),
    forecast_date  DATE           NOT NULL,  -- t: last data date used
    target_date    DATE           NOT NULL,  -- t + h
    horizon        SMALLINT       NOT NULL CHECK (horizon IN (1, 7, 14)),
    market         TEXT           NOT NULL,
    commodity      TEXT           NOT NULL,
    variety        TEXT           NOT NULL,
    p10            NUMERIC(12, 2) NOT NULL,
    p50            NUMERIC(12, 2) NOT NULL,
    p90            NUMERIC(12, 2) NOT NULL,
    last_value     NUMERIC(12, 2),            -- last observed price at forecast time
    model_name     TEXT,
    model_version  TEXT           NOT NULL,
    created_at     TIMESTAMPTZ    NOT NULL DEFAULT now(),
    PRIMARY KEY (forecast_date, horizon, commodity, market, variety)
);
CREATE INDEX IF NOT EXISTS ix_forecasts_target ON forecasts (commodity, market, target_date);

CREATE TABLE IF NOT EXISTS model_metrics (
    id             BIGSERIAL      PRIMARY KEY,
    run_id         BIGINT         REFERENCES pipeline_runs (run_id),
    model_name     TEXT           NOT NULL,
    model_version  TEXT,
    split          TEXT           NOT NULL CHECK (split IN ('backtest', 'live')),
    commodity      TEXT           NOT NULL,
    horizon        SMALLINT       NOT NULL,
    metric         TEXT           NOT NULL,  -- mape | smape | mase
    value          DOUBLE PRECISION NOT NULL,
    naive_value    DOUBLE PRECISION,
    computed_at    TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Serving (Phase 3; see migration 006)
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- Observe (Phase 4; see migration 007)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drift_reports (
    id               BIGSERIAL        PRIMARY KEY,
    report_date      DATE             NOT NULL UNIQUE,
    ref_start        DATE             NOT NULL,
    ref_end          DATE             NOT NULL,
    cur_start        DATE             NOT NULL,
    cur_end          DATE             NOT NULL,
    n_features       INTEGER          NOT NULL,
    n_drifted        INTEGER          NOT NULL,
    drift_share      DOUBLE PRECISION NOT NULL,
    target_drift     BOOLEAN          NOT NULL,
    target_p_value   DOUBLE PRECISION,
    mape_ratio_days  INTEGER,                 -- consecutive days champion live MAPE > 1.5x backtest
    escalated        BOOLEAN          NOT NULL DEFAULT FALSE,
    html_url         TEXT,                    -- Evidently HTML on the GitHub release reports-<date>
    details          JSONB,
    created_at       TIMESTAMPTZ      NOT NULL DEFAULT now()
);

-- Read paths of the API / dashboard (all small tables; keeps every query well under 1 s).
CREATE INDEX IF NOT EXISTS ix_forecasts_series ON forecasts (commodity, market, horizon, forecast_date);
CREATE INDEX IF NOT EXISTS ix_model_metrics_read ON model_metrics (split, model_name, computed_at);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_finished ON pipeline_runs (finished_at);

-- ---------------------------------------------------------------------------
-- Telegram bot, Stage 2 (Phase 5; see migration 008). Privacy: only chat_id, language,
-- alerts, digest subscriptions and timestamps -- no names, usernames or phone numbers.
-- ---------------------------------------------------------------------------
-- The Phase-1 placeholder `subscribers` (one row per chat x crop x market) was never used;
-- replace it with one row per chat. Refuses (fails the run) if it ever held data.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'subscribers'
                 AND column_name = 'threshold_pct') THEN
        IF EXISTS (SELECT 1 FROM subscribers) THEN
            RAISE EXCEPTION 'legacy subscribers table is not empty; migrate it by hand';
        END IF;
        DROP TABLE subscribers;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id           BIGINT       PRIMARY KEY,
    lang              TEXT         NOT NULL DEFAULT 'ml' CHECK (lang IN ('ml', 'en')),
    digest_crops      TEXT[]       NOT NULL DEFAULT '{}',   -- /subscribe <crop>: daily digest
    active            BOOLEAN      NOT NULL DEFAULT TRUE,   -- FALSE once the user blocks the bot
    last_digest_date  DATE,                                 -- one digest per day (idempotent)
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_active       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Price-threshold alerts on REAL prices (prices_clean), never on model output. Fires once per
-- crossing: armed -> triggered (message) -> armed again only after the price crosses back.
CREATE TABLE IF NOT EXISTS user_alerts (
    id               BIGSERIAL      PRIMARY KEY,
    chat_id          BIGINT         NOT NULL REFERENCES subscribers (chat_id) ON DELETE CASCADE,
    commodity        TEXT           NOT NULL,
    market           TEXT           NOT NULL,
    variety          TEXT           NOT NULL,
    direction        TEXT           NOT NULL CHECK (direction IN ('above', 'below')),
    threshold_rs_kg  NUMERIC(10, 2) NOT NULL CHECK (threshold_rs_kg > 0),
    state            TEXT           NOT NULL DEFAULT 'armed' CHECK (state IN ('armed', 'triggered')),
    active           BOOLEAN        NOT NULL DEFAULT TRUE,
    last_price_date  DATE,          -- latest observation already evaluated
    last_price_rs_kg NUMERIC(10, 2),
    n_triggered      INTEGER        NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT now(),
    triggered_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_user_alerts_chat ON user_alerts (chat_id) WHERE active;

-- Webhook dedupe: Telegram retries an update when a cold-starting instance answers slowly.
-- Kept 7 days (pruned by the daily user_alerts step). No chat ids, no message content.
CREATE TABLE IF NOT EXISTS telegram_updates (
    update_id    BIGINT       PRIMARY KEY,
    received_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Usage metrics: command / callback names and alert events only (never message text).
CREATE TABLE IF NOT EXISTS bot_events (
    id       BIGSERIAL    PRIMARY KEY,
    at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    chat_id  BIGINT,
    event    TEXT         NOT NULL,   -- command | callback | alert_created | alert_triggered | digest_sent | blocked | rate_limited
    detail   TEXT                     -- the command name, e.g. 'price'
);
CREATE INDEX IF NOT EXISTS ix_bot_events_at ON bot_events (at);

-- Aggregates for the read-only role (API badge, dashboard): no chat ids leave the database.
CREATE OR REPLACE VIEW bot_usage AS
SELECT
    (SELECT count(*) FROM subscribers WHERE active)::int AS users_active,
    (SELECT count(DISTINCT chat_id) FROM bot_events
      WHERE event IN ('command', 'callback') AND at > now() - interval '7 days')::int AS active_7d,
    (SELECT count(DISTINCT chat_id) FROM bot_events
      WHERE event IN ('command', 'callback') AND at > now() - interval '30 days')::int AS active_30d,
    (SELECT count(*) FROM bot_events
      WHERE event IN ('command', 'callback') AND at > now() - interval '30 days')::int AS commands_30d,
    (SELECT count(*) FROM user_alerts WHERE active)::int AS alerts_active,
    (SELECT count(*) FROM bot_events
      WHERE event = 'alert_created' AND at > now() - interval '30 days')::int AS alerts_created_30d,
    (SELECT count(*) FROM bot_events
      WHERE event = 'alert_triggered' AND at > now() - interval '30 days')::int AS alerts_triggered_30d,
    (SELECT count(*) FROM subscribers WHERE active AND cardinality(digest_crops) > 0)::int AS digest_users;

CREATE OR REPLACE VIEW bot_usage_daily AS
SELECT (at AT TIME ZONE 'Asia/Kolkata')::date AS day,
       count(DISTINCT chat_id) FILTER (WHERE event IN ('command', 'callback'))::int AS active_users,
       count(*) FILTER (WHERE event IN ('command', 'callback'))::int AS commands,
       count(*) FILTER (WHERE event = 'alert_triggered')::int AS alerts_triggered
FROM bot_events
WHERE at > now() - interval '90 days'
GROUP BY 1;
