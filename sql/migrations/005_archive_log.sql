-- Migration 005: which prices_raw rows were archived to GitHub Releases (Phase 2.5).
-- prices_raw keeps ~90 days in Neon; older rows live in release assets listed here.
-- clean --full and backfill read this table. Idempotent.
CREATE TABLE IF NOT EXISTS archive_log (
    release_tag  TEXT        PRIMARY KEY,   -- GitHub Release, e.g. data-archive-2026-10-07
    cutoff_date  DATE        NOT NULL,      -- rows dated < cutoff_date were archived
    rows         INTEGER     NOT NULL,
    archived_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
