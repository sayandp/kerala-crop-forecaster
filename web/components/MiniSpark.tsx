/**
 * Card sparkline: server-rendered inline SVG (no JS). Single series, so no legend; the card
 * text states the latest value and the 7-day change, so the line is decorative (aria-hidden).
 */
export function MiniSpark({ values, className = "h-10 w-full" }: { values: number[]; className?: string }) {
  if (values.length < 2) return <div className={className} aria-hidden="true" />;
  const W = 120;
  const H = 40;
  const pad = 3;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const x = (i: number) => pad + (i / (values.length - 1)) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((v - lo) / span) * (H - 2 * pad);
  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className={className} aria-hidden="true" focusable="false">
      <polyline
        points={`${pad},${H} ${pts} ${W - pad},${H}`}
        fill="var(--color-series-1)"
        fillOpacity={0.12}
        stroke="none"
      />
      <polyline
        points={pts}
        fill="none"
        stroke="var(--color-series-1)"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
