"use client";

// Recharts is the heaviest client bundle; load it after first paint so it never delays LCP.
import dynamic from "next/dynamic";

const placeholder = (h: string) =>
  function ChartPlaceholder() {
    return <div className={`${h} w-full animate-pulse rounded-xl bg-line/40`} />;
  };

export const PriceChart = dynamic(() => import("@/components/Charts").then((m) => m.PriceChart), {
  ssr: false,
  loading: placeholder("h-64"),
});

export const TrendChart = dynamic(() => import("@/components/Charts").then((m) => m.TrendChart), {
  ssr: false,
  loading: placeholder("h-56"),
});
