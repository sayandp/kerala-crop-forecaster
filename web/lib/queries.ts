// All dashboard reads. Parameterised tagged-template queries only; numerics are cast to
// float8 and dates formatted as text in SQL so the client never parses driver-specific types.
import { rows } from "@/lib/db";

export interface SeriesKey {
  commodity: string;
  market: string;
  variety: string;
}

export interface ForecastRow {
  horizon: number;
  as_of: string;
  target: string;
  p10: number;
  p50: number;
  p90: number;
  last_value: number | null;
  model_name: string | null;
  model_version: string;
}

export interface PricePoint {
  d: string;
  p: number;
}

export interface SeriesView {
  key: SeriesKey;
  forecasts: ForecastRow[];
  history: PricePoint[];
  lastObserved: string | null;
}

export async function seriesList(): Promise<SeriesKey[]> {
  return rows<SeriesKey>(
    (q) => q`SELECT DISTINCT commodity, market, variety FROM forecasts
             WHERE forecast_date = (SELECT max(forecast_date) FROM forecasts)
             ORDER BY commodity, market`,
  );
}

export interface Overview extends SeriesKey {
  as_of: string;
  last_value: number | null;
  last_observed: string | null;
  p10: number;
  p50: number;
  p90: number;
}

/** Latest 7-day forecast of every series, with the series' last observed date. */
export async function overview(): Promise<Overview[]> {
  return rows<Overview>(
    (q) => q`SELECT f.commodity, f.market, f.variety, to_char(f.forecast_date, 'YYYY-MM-DD') AS as_of,
                    f.last_value::float8 AS last_value,
                    (SELECT to_char(max(c.date), 'YYYY-MM-DD') FROM prices_clean c
                      WHERE c.commodity = f.commodity AND c.market = f.market
                        AND c.variety = f.variety) AS last_observed,
                    f.p10::float8 AS p10, f.p50::float8 AS p50, f.p90::float8 AS p90
             FROM forecasts f
             WHERE f.horizon = 7
               AND f.forecast_date = (SELECT max(forecast_date) FROM forecasts)
             ORDER BY f.commodity, f.market`,
  );
}

export async function seriesView(crop: string, market: string): Promise<SeriesView | null> {
  const forecasts = await rows<ForecastRow & { variety: string }>(
    (q) => q`SELECT horizon, variety, to_char(forecast_date, 'YYYY-MM-DD') AS as_of,
                    to_char(target_date, 'YYYY-MM-DD') AS target,
                    p10::float8 AS p10, p50::float8 AS p50, p90::float8 AS p90,
                    last_value::float8 AS last_value, model_name, model_version
             FROM forecasts
             WHERE commodity = ${crop} AND market = ${market}
               AND forecast_date = (SELECT max(forecast_date) FROM forecasts
                                    WHERE commodity = ${crop} AND market = ${market})
             ORDER BY horizon`,
  );
  const first = forecasts[0];
  if (!first) return null;
  const variety = first.variety;
  const history = await rows<PricePoint>(
    (q) => q`SELECT to_char(date, 'YYYY-MM-DD') AS d, modal_price::float8 AS p
             FROM prices_clean
             WHERE commodity = ${crop} AND market = ${market} AND variety = ${variety}
               AND date > (SELECT max(date) FROM prices_clean
                           WHERE commodity = ${crop} AND market = ${market}
                             AND variety = ${variety}) - 90
             ORDER BY date`,
  );
  return {
    key: { commodity: crop, market, variety },
    forecasts,
    history,
    lastObserved: history.at(-1)?.d ?? null,
  };
}

export interface LiveMetric {
  d: string;
  horizon: number;
  mape: number | null;
  naive: number | null;
  coverage: number | null;
}

export async function liveAccuracy(): Promise<LiveMetric[]> {
  return rows<LiveMetric>(
    (q) => q`SELECT to_char(computed_at::date, 'YYYY-MM-DD') AS d, horizon,
                    max(value) FILTER (WHERE metric = 'mape_28d') AS mape,
                    max(naive_value) FILTER (WHERE metric = 'mape_28d') AS naive,
                    max(value) FILTER (WHERE metric = 'coverage_80_28d') AS coverage
             FROM model_metrics
             WHERE split = 'live' AND model_name = 'champion' AND commodity = 'all'
             GROUP BY 1, 2 ORDER BY 1, 2`,
  );
}

export interface BacktestRow {
  model_name: string;
  horizon: number;
  mape: number;
}

export async function backtestMape(): Promise<BacktestRow[]> {
  return rows<BacktestRow>(
    (q) => q`SELECT DISTINCT ON (model_name, horizon) model_name, horizon, value AS mape
             FROM model_metrics
             WHERE split = 'backtest' AND commodity = 'all' AND metric = 'mape'
               AND model_name IN ('lgbm', 'naive')
             ORDER BY model_name, horizon, computed_at DESC`,
  );
}

export interface Decision {
  decided_at: string;
  model_name: string;
  scope: string;
  decision: string;
  challenger_version: string | null;
  champion_version: string | null;
  reason: string;
  dm_p: number | null;
  rel_pct: number | null;
}

export async function decisions(limit = 60): Promise<Decision[]> {
  return rows<Decision>(
    (q) => q`SELECT to_char(decided_at, 'YYYY-MM-DD HH24:MI') AS decided_at, model_name, scope,
                    decision, challenger_version, champion_version, reason,
                    (metrics->>'dm_p')::float8 AS dm_p,
                    (metrics->>'rel_improvement_pct')::float8 AS rel_pct
             FROM promotion_log ORDER BY decided_at DESC LIMIT ${limit}`,
  );
}

export interface ShadowRow {
  crop: string;
  n_evaluated: number;
  n_moves: number;
  days_covered: number;
  verdict: string;
}

export async function shadowProgress(): Promise<ShadowRow[]> {
  return rows<ShadowRow>(
    (q) => q`WITH latest AS (
               SELECT max(computed_at) AS t FROM model_metrics
               WHERE split = 'live' AND model_name = 'move-h7-shadow'),
             m AS (
               SELECT commodity,
                      max(value) FILTER (WHERE metric = 'n')::int AS n,
                      max(value) FILTER (WHERE metric = 'n_moves')::int AS n_moves,
                      max(value) FILTER (WHERE metric = 'days_covered')::int AS days_covered
               FROM model_metrics, latest
               WHERE split = 'live' AND model_name = 'move-h7-shadow'
                 AND computed_at >= latest.t - interval '1 hour'
               GROUP BY commodity),
             v AS (
               SELECT DISTINCT ON (scope) scope, decision FROM promotion_log
               WHERE model_name = 'cropcast-move-h7' ORDER BY scope, decided_at DESC)
             SELECT c.crop, coalesce(m.n, 0) AS n_evaluated, coalesce(m.n_moves, 0) AS n_moves,
                    coalesce(m.days_covered, 0) AS days_covered,
                    coalesce(v.decision, 'insufficient data') AS verdict
             FROM (VALUES ('coconut'), ('pepper'), ('rubber'), ('tapioca')) AS c(crop)
             LEFT JOIN m ON m.commodity = c.crop LEFT JOIN v ON v.scope = c.crop
             ORDER BY c.crop`,
  );
}

export interface DriftRow {
  report_date: string;
  drift_share: number;
  n_drifted: number;
  n_features: number;
  target_drift: boolean;
  target_p_value: number | null;
  escalated: boolean;
  html_url: string | null;
  reasons: string[] | null;
}

export async function driftHistory(): Promise<DriftRow[]> {
  return rows<DriftRow>(
    (q) => q`SELECT to_char(report_date, 'YYYY-MM-DD') AS report_date, drift_share, n_drifted,
                    n_features, target_drift, target_p_value, escalated, html_url,
                    details->'escalation_reasons' AS reasons
             FROM drift_reports ORDER BY report_date`,
  );
}

export interface RunRow {
  d: string;
  status: string;
  steps: string;
  db_mb: number | null;
}

export async function pipelineRuns(): Promise<RunRow[]> {
  return rows<RunRow>(
    (q) => q`SELECT to_char(started_at, 'YYYY-MM-DD HH24:MI') AS d, status, steps,
                    (details->>'db_size_mb')::float8 AS db_mb
             FROM pipeline_runs ORDER BY started_at DESC LIMIT 90`,
  );
}

export interface SubsRow {
  d: string;
  n: number;
}

export async function subscribers(): Promise<SubsRow[]> {
  return rows<SubsRow>(
    (q) => q`SELECT to_char(date, 'YYYY-MM-DD') AS d, member_count AS n
             FROM channel_stats ORDER BY date`,
  );
}
