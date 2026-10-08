-- Phase 5: Telegram bot (Stage 2). Mirrors sql/schema.sql; idempotent.
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
