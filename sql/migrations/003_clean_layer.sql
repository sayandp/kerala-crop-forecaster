-- Migration 003: clean layer (prices_raw is never mutated; prices_clean is derived from it).
-- Idempotent (IF NOT EXISTS); also present in sql/schema.sql.

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
    sources      TEXT           NOT NULL,
    PRIMARY KEY (commodity, market, variety, date)
);
