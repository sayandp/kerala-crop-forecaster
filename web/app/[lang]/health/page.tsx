import { TrendChart } from "@/components/LazyCharts";
import { Card, Empty, Page, Section, Table } from "@/components/ui";
import { dict } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";
import { botUsage, botUsageDaily, pipelineRuns, subscribers } from "@/lib/queries";

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
  const [runs, subs, bot, botDaily] = await Promise.all([
    pipelineRuns(),
    subscribers(),
    botUsage(),
    botUsageDaily(),
  ]);
  const lastOk = runs.find((r) => r.status === "success");
  const sizes = runs
    .filter((r) => r.db_mb !== null)
    .map((r) => ({ d: r.d.slice(0, 10), mb: r.db_mb }))
    .reverse();

  return (
    <>
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
        <Section title={t.bot}>
          {!bot ? (
            <Empty text={dict(lang).common.noData} />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Card>
                  <p className="text-sm text-muted">{t.botUsers}</p>
                  <p className="mt-1 text-2xl font-bold">{bot.users_active}</p>
                </Card>
                <Card>
                  <p className="text-sm text-muted">{t.botActive}</p>
                  <p className="mt-1 text-2xl font-bold">
                    {bot.active_7d} / {bot.active_30d}
                  </p>
                </Card>
                <Card>
                  <p className="text-sm text-muted">{t.botAlerts}</p>
                  <p className="mt-1 text-2xl font-bold">
                    {bot.alerts_active} / {bot.alerts_triggered_30d}
                  </p>
                </Card>
                <Card>
                  <p className="text-sm text-muted">{t.botDigest}</p>
                  <p className="mt-1 text-2xl font-bold">{bot.digest_users}</p>
                </Card>
              </div>
              {botDaily.length > 1 && (
                <div className="mt-4">
                  <p className="mb-2 text-sm text-muted">{t.botDaily}</p>
                  <TrendChart
                    data={botDaily.map((r) => ({ d: r.d, users: r.users }))}
                    series={[{ key: "users", label: t.botDaily, color: "var(--color-accent)" }]}
                  />
                </div>
              )}
              <p className="mt-2 text-xs text-muted">{t.botPrivacy}</p>
            </>
          )}
        </Section>
      </Page>
    </>
  );
}
