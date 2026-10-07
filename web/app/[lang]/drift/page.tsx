import { TrendChart } from "@/components/LazyCharts";
import { Footer, Nav } from "@/components/Nav";
import { Card, Empty, Page, Section } from "@/components/ui";
import { dict } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";
import { driftHistory } from "@/lib/queries";

export const revalidate = 3600;
export const generateStaticParams = langStaticParams;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).drift;
  return pageMetadata(lang, "/drift", t.title, t.intro);
}

export default async function Drift({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).drift;
  const reports = await driftHistory();
  const last = reports.at(-1);

  return (
    <>
      <Nav lang={lang} path="/drift" />
      <Page title={t.title} intro={t.intro}>
        {!last ? (
          <Empty text={t.none} />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Card>
                <p className="text-sm text-muted">{t.share}</p>
                <p className="mt-1 text-3xl font-bold">{Math.round(last.drift_share * 100)} %</p>
                <p className="text-sm text-muted">
                  {last.n_drifted} / {last.n_features} · {last.report_date}
                </p>
              </Card>
              <Card>
                <p className="text-sm text-muted">{t.target}</p>
                <p className={`mt-1 text-2xl font-bold ${last.target_drift ? "text-bad" : "text-good"}`}>
                  {last.target_drift ? t.drifted : t.stable}
                </p>
                {last.target_p_value !== null && (
                  <p className="text-sm text-muted">p = {last.target_p_value.toFixed(3)}</p>
                )}
              </Card>
            </div>
            {last.escalated && <p className="rounded-lg bg-warn/10 px-3 py-2 text-sm text-warn">{t.escalated}</p>}
            {last.html_url && (
              <a className="inline-block underline" href={last.html_url}>
                {t.report}
              </a>
            )}
            {reports.length > 1 && (
              <Section title={t.share}>
                <TrendChart
                  data={reports.map((r) => ({ d: r.report_date, share: r.drift_share * 100 }))}
                  series={[{ key: "share", label: t.share, color: "var(--color-accent)" }]}
                  reference={{ y: 30, label: "30 %" }}
                  unit="%"
                />
              </Section>
            )}
          </>
        )}
      </Page>
      <Footer lang={lang} />
    </>
  );
}
