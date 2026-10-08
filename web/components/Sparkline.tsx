import type { PriceChartPoint } from "@/components/Charts";

const W = 600;
const H = 256;
const PAD = 12;

/**
 * Inline-SVG stand-in for the price chart: rendered on the server (no JS), same box as the
 * Recharts chart (h-64), so the page paints the real price shape immediately and nothing shifts
 * when the interactive chart replaces it after first paint.
 */
export function Sparkline({ data }: { data: PriceChartPoint[] }) {
  const values = data.flatMap((p) => [p.price, ...(p.band ?? [])]).filter((v): v is number => v !== undefined);
  if (data.length < 2 || values.length === 0) {
    return <div className="h-64 w-full rounded-xl bg-line/40" aria-hidden="true" />;
  }
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const x = (i: number) => PAD + (i / (data.length - 1)) * (W - 2 * PAD);
  const y = (v: number) => H - PAD - ((v - lo) / span) * (H - 2 * PAD);

  const line = data
    .map((p, i) => (p.price === undefined ? null : `${x(i).toFixed(1)},${y(p.price).toFixed(1)}`))
    .filter((s): s is string => s !== null)
    .join(" ");
  const banded = data.map((p, i) => ({ i, band: p.band })).filter((p) => p.band !== undefined);
  const band =
    banded.length > 0
      ? [
          ...banded.map(({ i, band }) => `${x(i).toFixed(1)},${y(band![1]).toFixed(1)}`),
          ...banded.reverse().map(({ i, band }) => `${x(i).toFixed(1)},${y(band![0]).toFixed(1)}`),
        ].join(" ")
      : null;

  return (
    <svg
      className="h-64 w-full"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      {band && <polygon points={band} fill="var(--color-band)" />}
      <polyline
        points={line}
        fill="none"
        stroke="var(--color-series-1)"
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
