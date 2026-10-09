"use client";

import { useMemo, useState } from "react";
import type { PriceChartPoint } from "@/components/Charts";
import { PriceChart } from "@/components/LazyCharts";

type Range = "90" | "1y" | "5y";

export interface HistoryData {
  daily: { d: string; p: number }[]; // Rs./kg, last 365 days
  weekly: { d: string; p: number }[]; // Rs./kg, weekly mean, last 5 years
  band: { d: string; lo: number; hi: number }[]; // forecast p10-p90 at target dates
}

/** Segmented control (90 days / 1 year / 5 years) over the price chart + forecast band. */
export function HistoryPanel({
  data,
  labels,
}: {
  data: HistoryData;
  labels: { r90: string; r1y: string; r5y: string; price: string; band: string; group: string };
}) {
  const [range, setRange] = useState<Range>("90");
  const points = useMemo<PriceChartPoint[]>(() => {
    const base =
      range === "5y" ? data.weekly : range === "1y" ? data.daily : data.daily.slice(Math.max(0, data.daily.length - 90));
    const out: PriceChartPoint[] = base.map((x) => ({ d: x.d, price: x.p }));
    // The band opens at the last observed price and widens to each forecast horizon.
    const last = data.daily[data.daily.length - 1];
    if (last && data.band.length > 0) {
      const anchor = out.find((p) => p.d === last.d);
      if (anchor) anchor.band = [last.p, last.p];
    }
    for (const b of data.band) out.push({ d: b.d, band: [b.lo, b.hi] });
    return out.sort((a, b) => a.d.localeCompare(b.d));
  }, [data, range]);

  const options: [Range, string][] = [
    ["90", labels.r90],
    ["1y", labels.r1y],
    ["5y", labels.r5y],
  ];
  return (
    <div>
      <div role="group" aria-label={labels.group} className="mb-3 inline-flex rounded-full bg-line p-1">
        {options.map(([key, label]) => (
          <button
            key={key}
            type="button"
            aria-pressed={range === key}
            onClick={() => setRange(key)}
            className={`press min-h-11 rounded-full px-4 text-[14px] font-semibold ${
              range === key ? "bg-surface-solid text-ink shadow-sm" : "text-ink-2"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <PriceChart data={points} labels={{ price: labels.price, band: labels.band }} long={range === "5y"} />
    </div>
  );
}
