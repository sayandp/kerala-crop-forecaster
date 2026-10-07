import { Footer, Nav } from "@/components/Nav";
import { Empty, Page, Table } from "@/components/ui";
import { DAGSHUB } from "@/lib/format";
import { dict } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";
import { decisions } from "@/lib/queries";

export const revalidate = 3600;
export const generateStaticParams = langStaticParams;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).models;
  return pageMetadata(lang, "/models", t.title, t.intro);
}

export default async function Models({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).models;
  const log = await decisions();

  return (
    <>
      <Nav lang={lang} path="/models" />
      <Page title={t.title} intro={t.intro}>
        {log.length === 0 ? (
          <Empty text={dict(lang).common.noData} />
        ) : (
          <Table
            head={[t.when, t.model, t.scope, t.decision, t.challenger, t.champion, t.reason]}
            rows={log.map((d) => [
              <span key="w" className="whitespace-nowrap">{d.decided_at}</span>,
              d.model_name,
              d.scope,
              <strong key="d">{d.decision}</strong>,
              d.challenger_version ?? "–",
              d.champion_version ?? "–",
              <span key="r" className="text-muted">{d.reason}</span>,
            ])}
          />
        )}
        <a className="inline-block underline" href={DAGSHUB}>
          {t.registry}
        </a>
      </Page>
      <Footer lang={lang} />
    </>
  );
}
