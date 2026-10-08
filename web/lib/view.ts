// Server-side shaping of query rows into what the pages show. Prices arrive in Rs./quintal
// (Agmarknet) and leave as Rs./kg.
import { CROPS, REF_MARKET, type Crop } from "@/lib/crops";
import { STALE_DAYS, daysBetween } from "@/lib/format";
import type { Lang } from "@/lib/i18n";
import type { LatestRow, SeasonalRow, SparkRow } from "@/lib/queries";

export function kg(rsPerQuintal: number): number {
  const v = rsPerQuintal / 100;
  return v >= 20 ? Math.round(v) : Math.round(v * 10) / 10;
}

export function changePct(now: number | null, before: number | null): number | null {
  if (now === null || before === null || before === 0) return null;
  return ((now - before) / before) * 100;
}

export function isFresh(row: LatestRow): boolean {
  return row.d !== null && daysBetween(row.d, row.as_of) <= STALE_DAYS;
}

export interface CropCardData {
  crop: Crop;
  market: string;
  price: number | null;
  change: number | null;
  date: string | null;
  fresh: boolean;
  spark: number[];
  best: { market: string; price: number } | null;
}

export function cropCards(latest: LatestRow[], sparks: SparkRow[]): CropCardData[] {
  return CROPS.map((crop) => {
    const rows = latest.filter((r) => r.commodity === crop);
    const ref = rows.find((r) => r.market === REF_MARKET[crop]) ?? rows[0];
    const fresh = rows.filter((r) => isFresh(r) && r.p !== null);
    const top = [...fresh].sort((a, b) => (b.p ?? 0) - (a.p ?? 0))[0];
    return {
      crop,
      market: ref?.market ?? REF_MARKET[crop],
      price: ref?.p != null ? kg(ref.p) : null,
      change: ref ? changePct(ref.p, ref.p7) : null,
      date: ref?.d ?? null,
      fresh: ref ? isFresh(ref) : false,
      spark: sparks.filter((s) => s.commodity === crop).map((s) => s.p / 100),
      best: top && top.p !== null ? { market: top.market, price: kg(top.p) } : null,
    };
  });
}

export interface SeasonPointKg {
  w: number;
  now: number | null;
  last: number | null;
  avg: number | null;
}

/** Weekly means: this year, last year, and the mean of the 5 years before this one. */
export function seasonal(rows: SeasonalRow[], year: number): SeasonPointKg[] {
  const by = new Map<string, number>();
  for (const r of rows) by.set(`${r.y}:${r.w}`, r.p);
  const out: SeasonPointKg[] = [];
  for (let w = 1; w <= 53; w++) {
    const prev = [1, 2, 3, 4, 5]
      .map((k) => by.get(`${year - k}:${w}`))
      .filter((v): v is number => v !== undefined);
    const now = by.get(`${year}:${w}`);
    const last = by.get(`${year - 1}:${w}`);
    out.push({
      w,
      now: now === undefined ? null : kg(now),
      last: last === undefined ? null : kg(last),
      avg: prev.length >= 3 ? kg(prev.reduce((a, b) => a + b, 0) / prev.length) : null,
    });
  }
  return out.filter((p) => p.now !== null || p.last !== null || p.avg !== null);
}

export function monthName(month: number, lang: Lang): string {
  return new Date(Date.UTC(2020, month - 1, 1)).toLocaleDateString(lang === "ml" ? "ml-IN" : "en-IN", {
    month: "long",
    timeZone: "UTC",
  });
}

export function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? (s[m] as number) : ((s[m - 1] as number) + (s[m] as number)) / 2;
}
