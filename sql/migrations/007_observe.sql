-- Migration 007 (Phase 4, "serve + observe"): drift summaries + indexes for API/dashboard reads.
-- Idempotent.
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
