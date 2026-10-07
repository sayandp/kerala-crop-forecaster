import { TrendChart } from "@/components/LazyCharts";
import { Footer, Nav } from "@/components/Nav";
import { Card, Empty, Page, Section, Table } from "@/components/ui";
import { dict } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";
import { pipelineRuns, subscribers } from "@/lib/queries";

export const revalidate = 3600;
export const generateStaticParams = langStaticParams;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).health;
  return pageMetadata(lang, "/health", t.title, t.runs);
}

export default async function Health({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).health;
  const [runs, subs] = await Promise.all([pipelineRuns(), subscribers()]);
  const lastOk = runs.find((r) => r.status === "success");
  const sizes = runs
    .filter((r) => r.db_mb !== null)
    .map((r) => ({ d: r.d.slice(0, 10), mb: r.db_mb }))
    .reverse();

  return (
    <>
      <Nav lang={lang} path="/health" />
      <Page title={t.title}>
        {runs.length === 0 ? (
          <Empty text={dict(lang).common.noData} />
        ) : (
          <>
            <Card>
              <p className="text-sm text-muted">{t.lastOk}</p>
              <p className="mt-1 text-2xl font-bold">{lastOk?.d ?? "–"}</p>
            </Card>
            <Section title={t.runs}>
              <Table
                head={["", "", ""]}
                rows={runs.slice(0, 14).map((r) => [
                  <span key="d" className="whitespace-nowrap">{r.d}</span>,
                  <span
                    key="s"
                    className={r.status === "success" ? "text-good" : r.status === "failed" ? "text-bad" : "text-muted"}
                  >
                    {r.status}
                  </span>,
                  <span key="t" className="text-muted">{r.steps}</span>,
                ])}
              />
            </Section>
            {sizes.length > 0 && (
              <Section title={t.db}>
                <TrendChart
                  data={sizes}
                  series={[{ key: "mb", label: "MB", color: "var(--color-accent)" }]}
                  reference={{ y: 512, label: "512" }}
                />
              </Section>
            )}
          </>
        )}
        <Section title={t.subs}>
          {subs.length === 0 ? (
            <Empty text={dict(lang).common.noData} />
          ) : (
            <TrendChart data={subs.map((s) => ({ d: s.d, n: s.n }))} series={[{ key: "n", label: t.subs, color: "var(--color-good)" }]} />
          )}
        </Section>
      </Page>
      <Footer lang={lang} />
    </>
  );
}
