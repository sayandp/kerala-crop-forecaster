"use client";

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

const axis = { fontSize: 12, fill: "var(--color-muted)" };

/** Observed Rs./kg (line) plus the forecast band p10–p90 and median. */
export function PriceChart({ data, labels }: { data: PriceChartPoint[]; labels: { price: string; band: string } }) {
  return (
    <div className="h-64 w-full" role="img" aria-label={`${labels.price}, ${labels.band}`}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid stroke="var(--color-line)" vertical={false} />
          <XAxis dataKey="d" tick={axis} tickFormatter={(d: string) => d.slice(5)} minTickGap={24} />
          <YAxis tick={axis} domain={["auto", "auto"]} width={56} />
          <Tooltip />
          <Area
            dataKey="band"
            name={labels.band}
            stroke="none"
            fill="var(--color-band)"
            fillOpacity={0.9}
            isAnimationActive={false}
          />
          <Line
            dataKey="mid"
            name={labels.band}
            stroke="var(--color-accent)"
            strokeDasharray="4 3"
            dot={{ r: 3 }}
            isAnimationActive={false}
            legendType="none"
          />
          <Line
            dataKey="price"
            name={labels.price}
            stroke="var(--color-ink)"
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
          <CartesianGrid stroke="var(--color-line)" vertical={false} />
          <XAxis dataKey="d" tick={axis} tickFormatter={(d: string) => d.slice(5)} minTickGap={24} />
          <YAxis tick={axis} width={56} unit={unit} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {reference && (
            <ReferenceLine y={reference.y} stroke="var(--color-muted)" strokeDasharray="2 4" label={reference.label} />
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
