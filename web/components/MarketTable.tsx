"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

export interface MarketRow {
  market: string;
  name: string; // localized
  href: string;
  price: number | null; // Rs./kg
  change: number | null; // % vs ~7 days ago
  date: string | null; // localized short date
  iso: string | null;
  stale: boolean;
  lo: number | null;
  hi: number | null;
  current: boolean;
}

type Key = "name" | "price" | "change" | "iso";

export function MarketTable({
  rows,
  labels,
}: {
  rows: MarketRow[];
  labels: { market: string; price: string; change: string; date: string; range: string; sortBy: string; stale: string };
}) {
  const [sort, setSort] = useState<{ key: Key; dir: 1 | -1 }>({ key: "price", dir: -1 });
  const sorted = useMemo(() => {
    const val = (r: MarketRow): string | number => {
      const v = r[sort.key];
      return v ?? (sort.dir === 1 ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY);
    };
    return [...rows].sort((a, b) => {
      const x = val(a);
      const y = val(b);
      if (typeof x === "string" && typeof y === "string") return x.localeCompare(y) * sort.dir;
      return ((x as number) - (y as number)) * sort.dir;
    });
  }, [rows, sort]);

  const head: { key: Key; label: string; numeric: boolean }[] = [
    { key: "name", label: labels.market, numeric: false },
    { key: "price", label: labels.price, numeric: true },
    { key: "change", label: labels.change, numeric: true },
    { key: "iso", label: labels.date, numeric: false },
  ];

  return (
    <div className="surface-data overflow-x-auto">
      <table className="w-full min-w-[520px] text-left text-[15px]">
        <thead>
          <tr className="border-b border-line text-[13px] text-ink-2">
            {head.map((h) => {
              const on = sort.key === h.key;
              return (
                <th
                  key={h.key}
                  scope="col"
                  aria-sort={on ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
                  className={`px-3 py-1 font-semibold ${h.numeric ? "text-right" : ""}`}
                >
                  <button
                    type="button"
                    className="press inline-flex min-h-11 items-center gap-1 rounded-lg px-1"
                    onClick={() =>
                      setSort((s) => ({ key: h.key, dir: s.key === h.key ? (s.dir === 1 ? -1 : 1) : h.numeric ? -1 : 1 }))
                    }
                    aria-label={labels.sortBy.replace("{col}", h.label)}
                  >
                    {h.label}
                    <span aria-hidden="true" className={on ? "" : "opacity-30"}>
                      {on && sort.dir === 1 ? "↑" : "↓"}
                    </span>
                  </button>
                </th>
              );
            })}
            <th scope="col" className="px-3 py-1 text-right font-semibold">
              {labels.range}
            </th>
          </tr>
        </thead>
        <tbody className="tabular">
          {sorted.map((r) => (
            <tr key={r.market} className={`border-b border-line last:border-0 ${r.current ? "bg-accent-soft" : ""}`}>
              <th scope="row" className="px-3 py-2.5 font-semibold">
                <Link href={r.href} prefetch={false} className="underline decoration-line underline-offset-4">
                  {r.name}
                </Link>
              </th>
              <td className="px-3 py-2.5 text-right font-semibold">{r.price === null ? "–" : `₹${r.price}`}</td>
              <td className="px-3 py-2.5 text-right">
                {r.change === null ? "–" : `${r.change > 0 ? "▲ +" : r.change < 0 ? "▼ " : ""}${r.change.toFixed(1)}%`}
              </td>
              <td className="px-3 py-2.5 whitespace-nowrap">
                {r.date ?? "–"}
                {r.stale && (
                  <span className="ml-2 rounded-full bg-warn-soft px-2 py-0.5 text-[12px] font-semibold text-warn">
                    {labels.stale}
                  </span>
                )}
              </td>
              <td className="px-3 py-2.5 text-right whitespace-nowrap">
                {r.lo === null || r.hi === null ? "–" : `₹${r.lo}–${r.hi}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
