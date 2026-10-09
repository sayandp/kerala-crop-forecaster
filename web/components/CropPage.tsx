import Link from "next/link";
import { notFound } from "next/navigation";
import { CropIcon } from "@/components/CropIcon";
import { DataCard, GlassCard, PriceBadge, SectionTitle, TrendPill } from "@/components/glass";
import { HistoryPanel } from "@/components/HistoryPanel";
import { KeralaMap } from "@/components/KeralaMap";
import { SeasonChart } from "@/components/LazyCharts";
import { MarketTable, type MarketRow } from "@/components/MarketTable";
import { Sheet } from "@/components/Sheet";
import { botAlertLink, cropName, isCrop, marketName, REF_MARKET, type Crop } from "@/lib/crops";
import { shortDate } from "@/lib/format";
import { dict, fill, href, type Lang } from "@/lib/i18n";
import { MARKET_DISTRICT } from "@/lib/kerala-map";
import { cropDetail, latestAll } from "@/lib/queries";
import { changePct, isFresh, kg, median, monthName, seasonal } from "@/lib/view";

export function cropPath(crop: string, market?: string): string {
  return market ? `/crop/${crop}/${encodeURIComponent(market)}` : `/crop/${crop}`;
}

export async function CropPage({ lang, crop, market }: { lang: Lang; crop: string; market?: string }) {
  if (!isCrop(crop)) notFound();
  const t = dict(lang);
  const c = t.crop;
  const latest = (await latestAll()).filter((r) => r.commodity === crop);
  const wanted = market ?? REF_MARKET[crop as Crop];
  const row = latest.find((r) => r.market === wanted) ?? (market ? undefined : latest[0]);
  if (market && !row && latest.length > 0) notFound();
  const name = cropName(lang, crop);

  if (!row) {
    return (
      <main id="main" className="mx-auto max-w-5xl px-4 pt-6">
        <h1 className="text-[28px] font-bold">{name}</h1>
        <p className="surface-data mt-4 p-6 text-ink-2">{t.home.noData}</p>
      </main>
    );
  }

  const detail = await cropDetail(row);
  const mName = marketName(row.market, lang);
  const price = row.p === null ? null : kg(row.p);
  const lo = kg(row.p10);
  const hi = kg(row.p90);
  const year = row.d ? Number(row.d.slice(0, 4)) : new Date().getUTCFullYear();
  const season = seasonal(detail.seasonal, year);
  const pct = detail.percentile;
  const share = pct.share === null ? null : Math.round(pct.share * 100);
  const pctText =
    share === null || pct.month === null || pct.since === null
      ? null
      : fill(share >= 50 ? c.percentile : c.percentileLow, {
          pct: share >= 50 ? share : 100 - share,
          month: monthName(pct.month, lang),
          year: pct.since,
        });

  const rows: MarketRow[] = latest.map((r) => ({
    market: r.market,
    name: marketName(r.market, lang),
    href: href(lang, cropPath(crop, r.market)),
    price: r.p === null ? null : kg(r.p),
    change: changePct(r.p, r.p7),
    date: r.d ? shortDate(r.d, lang) : null,
    iso: r.d,
    stale: !isFresh(r),
    lo: kg(r.p10),
    hi: kg(r.p90),
    current: r.market === row.market,
  }));

  const byDistrict = new Map<string, number[]>();
  for (const r of latest) {
    const d = MARKET_DISTRICT[r.market];
    if (!d || r.p === null || !isFresh(r)) continue;
    byDistrict.set(d, [...(byDistrict.get(d) ?? []), r.p]);
  }
  const mapValues = Object.fromEntries([...byDistrict].map(([d, ps]) => [d, kg(median(ps))]));

  const history = {
    daily: detail.daily.map((x) => ({ d: x.d, p: x.p / 100 })),
    weekly: detail.weekly.map((x) => ({ d: x.d, p: x.p / 100 })),
    band: detail.forecasts.map((f) => ({ d: f.target, lo: f.p10 / 100, hi: f.p90 / 100 })),
  };
  const shareText = fill(c.shareText, {
    crop: name,
    market: mName,
    price: price ?? "–",
    date: row.d ? shortDate(row.d, lang) : "–",
    lo,
    hi,
  });
  const pageUrl = `https://kerala-crop-forecaster.vercel.app${href(lang, cropPath(crop, market))}`;

  return (
    <main id="main" className="mx-auto max-w-5xl space-y-8 px-4 pt-6">
      <header className="flex flex-wrap items-center gap-3">
        <span className="grid h-12 w-12 place-items-center rounded-[16px] bg-accent-soft text-accent">
          <CropIcon crop={crop as Crop} />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="text-[28px] leading-tight font-bold tracking-tight md:text-[34px]">{name}</h1>
          <p className="text-[15px] text-ink-2">
            {c.market}: <span className="font-semibold text-ink">{mName}</span>
          </p>
        </div>
        <Sheet label={c.changeMarket} title={c.pickMarket} closeLabel={c.close}>
          <ul className="grid gap-2 pb-2">
            {rows
              .slice()
              .sort((a, b) => a.name.localeCompare(b.name))
              .map((r) => (
                <li key={r.market}>
                  <Link
                    href={r.href}
                    prefetch={false}
                    aria-current={r.current ? "page" : undefined}
                    className={`press flex min-h-12 items-center justify-between rounded-[16px] px-4 text-[16px] ${
                      r.current ? "bg-accent text-accent-ink" : "surface-data"
                    }`}
                  >
                    <span className="font-semibold">{r.name}</span>
                    <span className="tabular">{r.price === null ? "–" : `₹${r.price}`}</span>
                  </Link>
                </li>
              ))}
          </ul>
        </Sheet>
      </header>

      <section aria-labelledby="today" className="grid gap-4 md:grid-cols-2">
        <DataCard>
          <h2 id="today" className="text-[15px] text-ink-2">
            {fill(c.today, { market: mName })}
          </h2>
          <div className="mt-2 flex flex-wrap items-end justify-between gap-2">
            <PriceBadge value={price === null ? "–" : `₹${price}`} unit={t.prices.perKg} />
            <TrendPill pct={changePct(row.p, row.p7)} label={t.home.vs7} />
          </div>
          <p className="mt-2 text-[13px] text-ink-2">
            {t.home.updated} {row.d ? shortDate(row.d, lang) : "–"}
            {!isFresh(row) && <span className="ml-2 font-semibold text-warn">⚠ {t.prices.stale}</span>}
          </p>
          {pctText && (
            <p className="mt-3 inline-flex rounded-full bg-accent-soft px-3 py-1.5 text-[14px] font-semibold text-accent">
              {pctText}
            </p>
          )}
        </DataCard>
        <DataCard>
          <h2 className="text-[15px] text-ink-2">{c.range7}</h2>
          <PriceBadge value={`₹${lo}–${hi}`} unit={t.prices.perKg} />
          <p className="mt-2 text-[13px] text-ink-2">{shortDate(row.target, lang)}</p>
          <p className="mt-3 text-[13px] leading-relaxed text-ink-2">{c.rangeNote}</p>
        </DataCard>
      </section>

      <GlassCard as="section" className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-bold">{c.alert}</h2>
          <p className="text-[14px] text-ink-2">{c.alertLead}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            href={botAlertLink(crop, row.market)}
            target="_blank"
            rel="noopener noreferrer"
            className="press inline-flex min-h-11 items-center rounded-full bg-accent px-5 text-[15px] font-semibold text-accent-ink"
          >
            {c.alert}
          </a>
          <a
            href={`https://wa.me/?text=${encodeURIComponent(`${shareText} ${pageUrl}`)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="press surface-data inline-flex min-h-11 items-center !rounded-full px-5 text-[15px] font-semibold"
          >
            {c.share}
          </a>
        </div>
      </GlassCard>

      <section aria-labelledby="history">
        <SectionTitle id="history">{c.history}</SectionTitle>
        <DataCard>
          <HistoryPanel
            data={history}
            labels={{ r90: c.r90, r1y: c.r1y, r5y: c.r5y, price: c.price, band: c.band, group: c.history }}
          />
        </DataCard>
      </section>

      {season.length > 0 && (
        <section aria-labelledby="high">
          <SectionTitle id="high">{c.high}</SectionTitle>
          <p className="-mt-1 mb-3 text-[14px] text-ink-2">{fill(c.highLead, { market: mName })}</p>
          <DataCard>
            <SeasonChart
              data={season}
              year={year}
              labels={{ now: c.thisYear, last: c.lastYear, avg: c.avg5, week: c.week }}
            />
            <details className="mt-3">
              <summary className="press inline-flex min-h-11 cursor-pointer items-center font-semibold text-accent">
                {c.table}
              </summary>
              <div className="mt-2 max-h-80 overflow-y-auto">
                <table className="tabular w-full text-[14px]">
                  <thead className="text-ink-2">
                    <tr>
                      <th scope="col" className="py-1 text-left">{c.week}</th>
                      <th scope="col" className="py-1 text-right">{c.thisYear}</th>
                      <th scope="col" className="py-1 text-right">{c.lastYear}</th>
                      <th scope="col" className="py-1 text-right">{c.avg5}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {season.map((s) => (
                      <tr key={s.w} className="border-t border-line">
                        <th scope="row" className="py-1 text-left font-normal">{s.w}</th>
                        <td className="py-1 text-right">{s.now === null ? "–" : `₹${s.now}`}</td>
                        <td className="py-1 text-right">{s.last === null ? "–" : `₹${s.last}`}</td>
                        <td className="py-1 text-right">{s.avg === null ? "–" : `₹${s.avg}`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </DataCard>
        </section>
      )}

      <section aria-labelledby="markets">
        <SectionTitle id="markets">{c.markets}</SectionTitle>
        <MarketTable
          rows={rows}
          labels={{
            market: c.colMarket,
            price: c.colPrice,
            change: c.colChange,
            date: c.colDate,
            range: c.colRange,
            sortBy: c.sortBy,
            stale: c.stale,
          }}
        />
      </section>

      {Object.keys(mapValues).length > 0 && (
        <section aria-labelledby="map">
          <SectionTitle id="map">{c.map}</SectionTitle>
          <p className="-mt-1 mb-3 text-[14px] text-ink-2">{c.mapLead}</p>
          <KeralaMap values={mapValues} lang={lang} title={c.map} none={c.mapNone} />
        </section>
      )}
    </main>
  );
}
