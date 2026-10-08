"use client";

// Recharts charts (loaded lazily after first paint; see LazyCharts). Mark specs per the dataviz
// method: 2px lines, recessive grid/axes, text in ink tokens (never the series colour), legend for
// >= 2 series plus direct end labels, a crosshair tooltip on every line chart.
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface PriceChartPoint {
  d: string;
  price?: number;
  band?: [number, number];
  mid?: number;
}

const axis = { fontSize: 12, fill: "var(--color-ink-2)" };
const grid = "var(--color-line)";

function TooltipBox({
  active,
  label,
  payload,
  fmtLabel,
}: {
  active?: boolean;
  label?: string | number;
  payload?: { name?: string; value?: unknown; color?: string }[];
  fmtLabel?: (l: string) => string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="surface-data px-3 py-2 text-[13px] shadow-lg">
      <p className="mb-1 font-semibold">{fmtLabel ? fmtLabel(String(label)) : String(label)}</p>
      {payload.map((p) => {
        const v = p.value;
        const text = Array.isArray(v)
          ? `₹${Number(v[0]).toFixed(0)}–${Number(v[1]).toFixed(0)}`
          : typeof v === "number"
            ? `₹${v.toFixed(v >= 100 ? 0 : 1)}`
            : String(v ?? "");
        return (
          <p key={p.name} className="tabular flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-2 w-3 rounded-full" style={{ background: p.color }} />
            <span className="text-ink-2">{p.name}</span>
            <span className="ml-auto font-semibold">{text}</span>
          </p>
        );
      })}
    </div>
  );
}

/** Observed Rs./kg (one series, slot 1) plus the forecast band p10–p90 (blue 100). */
export function PriceChart({
  data,
  labels,
  long = false,
}: {
  data: PriceChartPoint[];
  labels: { price: string; band: string };
  long?: boolean;
}) {
  const fmt = (d: string) => (long ? d.slice(0, 7) : d.slice(5));
  return (
    <div className="h-64 w-full" role="img" aria-label={`${labels.price}, ${labels.band}`}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="d" tick={axis} tickFormatter={fmt} minTickGap={28} stroke={grid} />
          <YAxis tick={axis} domain={["auto", "auto"]} width={52} stroke={grid} tickFormatter={(v: number) => `₹${v}`} />
          <Tooltip content={<TooltipBox />} cursor={{ stroke: "var(--color-ink-2)", strokeDasharray: "3 3" }} />
          <Area dataKey="band" name={labels.band} stroke="none" fill="var(--color-band)" fillOpacity={1} isAnimationActive={false} />
          <Line
            dataKey="price"
            name={labels.price}
            stroke="var(--color-series-1)"
            strokeWidth={2}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export interface SeasonPoint {
  w: number;
  now?: number | null;
  last?: number | null;
  avg?: number | null;
}

/** This year vs last year vs 5-year average by week (slots 1-3; 5-year dashed; end labels). */
export function SeasonChart({
  data,
  labels,
}: {
  data: SeasonPoint[];
  labels: { now: string; last: string; avg: string; week: string };
}) {
  const series = [
    { key: "now", name: labels.now, color: "var(--color-series-1)", dash: undefined },
    { key: "last", name: labels.last, color: "var(--color-series-2)", dash: undefined },
    { key: "avg", name: labels.avg, color: "var(--color-series-3)", dash: "6 4" },
  ] as const;
  const lastIndex = (k: (typeof series)[number]["key"]) => {
    for (let i = data.length - 1; i >= 0; i--) if (data[i]?.[k] != null) return i;
    return -1;
  };
  return (
    <div className="h-72 w-full" role="img" aria-label={`${labels.now}, ${labels.last}, ${labels.avg}`}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 64, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="w" tick={axis} stroke={grid} interval={7} tickFormatter={(w: number) => `${labels.week} ${w}`} />
          <YAxis tick={axis} width={52} stroke={grid} domain={["auto", "auto"]} tickFormatter={(v: number) => `₹${v}`} />
          <Tooltip
            content={<TooltipBox fmtLabel={(l) => `${labels.week} ${l}`} />}
            cursor={{ stroke: "var(--color-ink-2)", strokeDasharray: "3 3" }}
          />
          <Legend wrapperStyle={{ fontSize: 13, color: "var(--color-ink-2)" }} iconType="plainline" />
          {series.map((s) => {
            const end = lastIndex(s.key);
            return (
              <Line
                key={s.key}
                dataKey={s.key}
                name={s.name}
                stroke={s.color}
                strokeWidth={2}
                strokeDasharray={s.dash}
                dot={false}
                connectNulls
                isAnimationActive={false}
                label={(p: { index?: number; x?: number | string; y?: number | string }) =>
                  p.index === end ? (
                    <text
                      key={`${s.key}-label`}
                      x={Number(p.x) + 6}
                      y={Number(p.y)}
                      dominantBaseline="middle"
                      fontSize={12}
                      fontWeight={600}
                      fill="var(--color-ink-2)"
                    >
                      {s.name}
                    </text>
                  ) : (
                    <g key={`${s.key}-${p.index}`} />
                  )
                }
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export interface TrendPoint {
  d: string;
  [series: string]: number | string | null;
}

export function TrendChart({
  data,
  series,
  reference,
  unit = "",
}: {
  data: TrendPoint[];
  series: { key: string; label: string; color: string; dashed?: boolean }[];
  reference?: { y: number; label: string };
  unit?: string;
}) {
  return (
    <div className="h-56 w-full" role="img" aria-label={series.map((s) => s.label).join(", ")}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="d" tick={axis} tickFormatter={(d: string) => d.slice(5)} minTickGap={24} stroke={grid} />
          <YAxis tick={axis} width={56} unit={unit} stroke={grid} />
          <Tooltip />
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
          {reference && (
            <ReferenceLine y={reference.y} stroke="var(--color-ink-2)" strokeDasharray="2 4" label={reference.label} />
          )}
          {series.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              strokeDasharray={s.dashed ? "5 4" : undefined}
              dot={data.length < 15}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
