import type { PriceChartPoint } from "@/components/Charts";
import { PriceChart } from "@/components/LazyCharts";
import { SeriesPicker } from "@/components/SeriesPicker";
import { Card, Empty, Section, Table } from "@/components/ui";
import { STALE_DAYS, daysBetween, perKg, rupees, shortDate, TELEGRAM_CHANNEL } from "@/lib/format";
import { dict, fill, href, type Lang } from "@/lib/i18n";
import type { Overview, SeriesView } from "@/lib/queries";

export function seriesPath(crop: string, market: string): string {
  return `/p/${encodeURIComponent(crop)}/${encodeURIComponent(market)}`;
}

function cropName(lang: Lang, crop: string): string {
  const crops = dict(lang).crops as Record<string, string>;
  return crops[crop] ?? crop;
}

export function SeriesDetail({
  lang,
  view,
  all,
}: {
  lang: Lang;
  view: SeriesView | null;
  all: Overview[];
}) {
  const t = dict(lang);
  if (!view) return <Empty text={t.common.noData} />;

  const { key, forecasts, history, lastObserved } = view;
  const h7 = forecasts.find((f) => f.horizon === 7);
  const asOf = forecasts[0]?.as_of ?? "";
  const stale = lastObserved ? daysBetween(lastObserved, asOf) > STALE_DAYS : true;
  const last = history.at(-1)?.p ?? h7?.last_value ?? null;

  const chart: PriceChartPoint[] = history.map((h) => ({ d: h.d, price: perKg(h.p) }));
  for (const f of forecasts) {
    chart.push({ d: f.target, band: [perKg(f.p10), perKg(f.p90)], mid: perKg(f.p50) });
  }
  chart.sort((a, b) => a.d.localeCompare(b.d));

  const options = all.map((o) => ({
    value: href(lang, seriesPath(o.commodity, o.market)),
    label: `${cropName(lang, o.commodity)} · ${o.market}`,
  }));

  return (
    <>
      <SeriesPicker
        label={t.prices.pick}
        options={options}
        current={href(lang, seriesPath(key.commodity, key.market))}
      />

      <div className="grid grid-cols-2 gap-3">
        <Card>
          <p className="text-sm text-muted">{t.prices.latest}</p>
          <p className="mt-1 text-3xl font-bold">{last !== null ? rupees(last) : "–"}</p>
          <p className="text-sm text-muted">{t.prices.perKg}</p>
          {lastObserved && (
            <p className="mt-2 text-xs text-muted">
              {t.prices.observed} {shortDate(lastObserved, lang)}
            </p>
          )}
        </Card>
        <Card className="border-accent">
          <p className="text-sm text-muted">{t.prices.range7}</p>
          <p className="mt-1 text-3xl font-bold text-accent">
            {h7 ? `${rupees(h7.p10)}–${rupees(h7.p90).slice(1)}` : "–"}
          </p>
          <p className="text-sm text-muted">{t.prices.perKg}</p>
          {h7 && <p className="mt-2 text-xs text-muted">{shortDate(h7.target, lang)}</p>}
        </Card>
      </div>

      <p
        className={`rounded-lg px-3 py-2 text-sm ${stale ? "bg-warn/10 text-warn" : "bg-good/10 text-good"}`}
        role="status"
      >
        {stale ? t.prices.stale : t.prices.fresh} · {t.prices.asOf} {asOf && shortDate(asOf, lang)}
      </p>

      <Section title={t.prices.history}>
        <PriceChart data={chart} labels={{ price: t.prices.latest, band: t.prices.range }} />
      </Section>

      <Table
        head={["", t.prices.range, "p50"]}
        rows={forecasts.map((f) => [
          fill(t.prices.horizon, { h: f.horizon }),
          `${rupees(f.p10)}–${rupees(f.p90).slice(1)}`,
          rupees(f.p50),
        ])}
      />
      <p className="text-sm text-muted">{t.prices.note}</p>

      <Card className="flex flex-wrap items-center justify-between gap-3">
        <p>{t.prices.subscribe}</p>
        <a href={TELEGRAM_CHANNEL} className="rounded-lg bg-accent px-4 py-2 font-medium text-paper">
          {t.prices.subscribeCta}
        </a>
      </Card>
    </>
  );
}

export { cropName };
