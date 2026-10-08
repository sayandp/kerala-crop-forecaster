import { TrendChart } from "@/components/LazyCharts";
import { Card, Empty, Page, Section, Table } from "@/components/ui";
import { REPO } from "@/lib/format";
import { dict } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";
import { backtestMape, liveAccuracy } from "@/lib/queries";

export const revalidate = 3600;
export const generateStaticParams = langStaticParams;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).accuracy;
  return pageMetadata(lang, "/accuracy", t.title, t.intro);
}

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${v.toFixed(1)} %`);

export default async function Accuracy({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).accuracy;
  const [live, backtest] = await Promise.all([liveAccuracy(), backtestMape()]);
  const live7 = live.filter((r) => r.horizon === 7);
  const bt = (model: string, h: number) => backtest.find((b) => b.model_name === model && b.horizon === h)?.mape;

  return (
    <>
      <Page title={t.title} intro={t.intro}>
        <Section title={t.mape}>
          {live7.length === 0 ? (
            <Empty text={t.noData} />
          ) : (
            <TrendChart
              data={live7.map((r) => ({ d: r.d, champion: r.mape, naive: r.naive }))}
              series={[
                { key: "champion", label: t.champion, color: "var(--color-accent)" },
                { key: "naive", label: t.naive, color: "var(--color-muted)", dashed: true },
              ]}
              unit="%"
            />
          )}
        </Section>

        {live7.length > 0 && (
          <Section title={t.coverage}>
            <TrendChart
              data={live7.map((r) => ({ d: r.d, coverage: r.coverage }))}
              series={[{ key: "coverage", label: t.coverage, color: "var(--color-good)" }]}
              reference={{ y: 80, label: t.target }}
              unit="%"
            />
          </Section>
        )}

        <Section title={t.backtest}>
          <Table
            head={["", "h = 1", "h = 7", "h = 14"]}
            rows={[
              [t.naive, pct(bt("naive", 1)), pct(bt("naive", 7)), pct(bt("naive", 14))],
              ["LightGBM", pct(bt("lgbm", 1)), pct(bt("lgbm", 7)), pct(bt("lgbm", 14))],
            ]}
          />
        </Section>

        <Card>
          <h2 className="font-bold">{t.whyTitle}</h2>
          <p className="mt-2 leading-relaxed">{t.why}</p>
          <a className="mt-3 inline-block underline" href={`${REPO}/blob/main/reports/phase2_5_signal_hunt.md`}>
            {t.report}
          </a>
        </Card>
      </Page>
    </>
  );
}
