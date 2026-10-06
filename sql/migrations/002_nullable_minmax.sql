-- Migration 002: min_price / max_price become nullable.
-- Some markets (99 % VFPCK) report only the modal price, published as min = max = 0. Those
-- rows were quarantined by min <= modal <= max; they are now stored with NULL bounds.
-- Idempotent: DROP NOT NULL on an already-nullable column is a no-op.
ALTER TABLE prices_raw ALTER COLUMN min_price DROP NOT NULL;
ALTER TABLE prices_raw ALTER COLUMN max_price DROP NOT NULL;
