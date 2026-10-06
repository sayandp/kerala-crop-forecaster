-- Migration 004: arrival quantity (metric tonnes) alongside prices (Phase 2.5, E1).
-- Agmarknet publishes arrivals with every price report; NULL when not reported
-- (e.g. data.gov.in rows). prices_clean holds the SUM over a series-day's reports.
-- Idempotent (ADD COLUMN IF NOT EXISTS).
ALTER TABLE prices_raw      ADD COLUMN IF NOT EXISTS arrivals_tonnes NUMERIC(12, 3);
ALTER TABLE prices_rejected ADD COLUMN IF NOT EXISTS arrivals_tonnes NUMERIC(12, 3);
ALTER TABLE prices_clean    ADD COLUMN IF NOT EXISTS arrivals_tonnes NUMERIC(12, 3);
