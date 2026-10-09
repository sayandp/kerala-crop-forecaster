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

export interface BotUsage {
  users_active: number;
  active_7d: number;
  active_30d: number;
  commands_30d: number;
  alerts_active: number;
  alerts_created_30d: number;
  alerts_triggered_30d: number;
  digest_users: number;
}

/** Aggregates only (view bot_usage): the read-only role never sees chat ids. */
export async function botUsage(): Promise<BotUsage | null> {
  const r = await rows<BotUsage>((q) => q`SELECT * FROM bot_usage`);
  return r[0] ?? null;
}

export interface BotDay {
  d: string;
  users: number;
  commands: number;
}

export async function botUsageDaily(): Promise<BotDay[]> {
  return rows<BotDay>(
    (q) => q`SELECT to_char(day, 'YYYY-MM-DD') AS d, active_users AS users, commands
             FROM bot_usage_daily ORDER BY day`,
  );
}

// --- Phase 6: farmer-first pages ---------------------------------------------------------------

export interface LatestRow extends SeriesKey {
  as_of: string;
  target: string;
  p10: number;
  p90: number;
  d: string | null;
  p: number | null;
  p7: number | null;
}

/**
 * Every served series (latest forecast run): latest observed price, the price about a week
 * earlier (latest on or before date-7, within 14 days) and the 7-day forecast range.
 * PK-indexed lateral lookups over ~20 series: well under 1 s.
 */
export async function latestAll(): Promise<LatestRow[]> {
  return rows<LatestRow>(
    (q) => q`WITH s AS (
               SELECT commodity, market, variety, forecast_date, target_date, p10, p90
               FROM forecasts
               WHERE horizon = 7 AND forecast_date = (SELECT max(forecast_date) FROM forecasts))
             SELECT s.commodity, s.market, s.variety,
                    to_char(s.forecast_date, 'YYYY-MM-DD') AS as_of,
                    to_char(s.target_date, 'YYYY-MM-DD') AS target,
                    s.p10::float8 AS p10, s.p90::float8 AS p90,
                    to_char(l.date, 'YYYY-MM-DD') AS d, l.modal_price::float8 AS p,
                    w.modal_price::float8 AS p7
             FROM s
             LEFT JOIN LATERAL (
               SELECT date, modal_price FROM prices_clean c
               WHERE c.commodity = s.commodity AND c.market = s.market AND c.variety = s.variety
               ORDER BY date DESC LIMIT 1) l ON TRUE
             LEFT JOIN LATERAL (
               SELECT modal_price FROM prices_clean c
               WHERE c.commodity = s.commodity AND c.market = s.market AND c.variety = s.variety
                 AND c.date <= l.date - 7 AND c.date >= l.date - 14
               ORDER BY date DESC LIMIT 1) w ON TRUE
             ORDER BY s.commodity, s.market`,
  );
}

export interface SparkRow {
  commodity: string;
  d: string;
  p: number;
}

/** Last 90 days of the given series (one per crop) for the home-card sparklines. */
export async function sparklines(series: SeriesKey[]): Promise<SparkRow[]> {
  if (series.length === 0) return [];
  const c = series.map((s) => s.commodity);
  const m = series.map((s) => s.market);
  const v = series.map((s) => s.variety);
  return rows<SparkRow>(
    (q) => q`SELECT s.c AS commodity, to_char(p.date, 'YYYY-MM-DD') AS d,
                    p.modal_price::float8 AS p
             FROM unnest(${c}::text[], ${m}::text[], ${v}::text[]) AS s(c, m, v)
             JOIN LATERAL (
               SELECT date, modal_price FROM prices_clean x
               WHERE x.commodity = s.c AND x.market = s.m AND x.variety = s.v
                 AND x.date > (SELECT max(date) FROM prices_clean y
                               WHERE y.commodity = s.c AND y.market = s.m
                                 AND y.variety = s.v) - 90) p ON TRUE
             ORDER BY 1, 2`,
  );
}

export interface SeasonalRow {
  y: number;
  w: number;
  p: number;
}

export interface Percentile {
  share: number | null;
  since: number | null;
  month: number | null;
}

export interface CropDetail {
  daily: PricePoint[]; // last 365 days
  weekly: PricePoint[]; // last 5 years, weekly mean (the 5-year view)
  seasonal: SeasonalRow[];
  percentile: Percentile;
  forecasts: ForecastRow[];
}

/** One series: history, seasonal weekly means, month percentile and the latest forecasts. */
export async function cropDetail(key: SeriesKey): Promise<CropDetail> {
  const { commodity: c, market: m, variety: v } = key;
  const [daily, weekly, seasonal, pct, forecasts] = await Promise.all([
    rows<PricePoint>(
      (q) => q`SELECT to_char(date, 'YYYY-MM-DD') AS d, modal_price::float8 AS p
               FROM prices_clean
               WHERE commodity = ${c} AND market = ${m} AND variety = ${v}
                 AND date > (SELECT max(date) FROM prices_clean
                             WHERE commodity = ${c} AND market = ${m} AND variety = ${v}) - 365
               ORDER BY date`,
    ),
    rows<PricePoint>(
      (q) => q`SELECT to_char(date_trunc('week', date), 'YYYY-MM-DD') AS d,
                      avg(modal_price)::float8 AS p
               FROM prices_clean
               WHERE commodity = ${c} AND market = ${m} AND variety = ${v}
                 AND date > (SELECT max(date) FROM prices_clean
                             WHERE commodity = ${c} AND market = ${m} AND variety = ${v}) - 1827
               GROUP BY 1 ORDER BY 1`,
    ),
    rows<SeasonalRow>(
      (q) => q`SELECT extract(isoyear FROM date)::int AS y, extract(week FROM date)::int AS w,
                      avg(modal_price)::float8 AS p
               FROM prices_clean
               WHERE commodity = ${c} AND market = ${m} AND variety = ${v}
                 AND date >= make_date(extract(year FROM now())::int - 6, 1, 1)
               GROUP BY 1, 2 ORDER BY 1, 2`,
    ),
    rows<Percentile>(
      (q) => q`WITH l AS (
                 SELECT date, modal_price FROM prices_clean
                 WHERE commodity = ${c} AND market = ${m} AND variety = ${v}
                 ORDER BY date DESC LIMIT 1)
               SELECT (count(*) FILTER (WHERE x.modal_price < l.modal_price))::float8
                        / NULLIF(count(*), 0) AS share,
                      min(extract(year FROM x.date))::int AS since,
                      extract(month FROM l.date)::int AS month
               FROM l JOIN prices_clean x
                 ON x.commodity = ${c} AND x.market = ${m} AND x.variety = ${v}
                AND extract(month FROM x.date) = extract(month FROM l.date)
                AND x.date < date_trunc('month', l.date)
               GROUP BY l.date`,
    ),
    rows<ForecastRow>(
      (q) => q`SELECT horizon, to_char(forecast_date, 'YYYY-MM-DD') AS as_of,
                      to_char(target_date, 'YYYY-MM-DD') AS target,
                      p10::float8 AS p10, p50::float8 AS p50, p90::float8 AS p90,
                      last_value::float8 AS last_value, model_name, model_version
               FROM forecasts
               WHERE commodity = ${c} AND market = ${m} AND variety = ${v}
                 AND forecast_date = (SELECT max(forecast_date) FROM forecasts
                                      WHERE commodity = ${c} AND market = ${m})
               ORDER BY horizon`,
    ),
  ]);
  return {
    daily,
    weekly,
    seasonal,
    percentile: pct[0] ?? { share: null, since: null, month: null },
    forecasts,
  };
}
