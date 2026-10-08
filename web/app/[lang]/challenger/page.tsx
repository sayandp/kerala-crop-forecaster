import { cropName } from "@/lib/crops";
import { Card, Page, Section, Table } from "@/components/ui";
import { REPO } from "@/lib/format";
import { dict } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";
import { shadowProgress } from "@/lib/queries";

export const revalidate = 3600;
export const generateStaticParams = langStaticParams;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).challenger;
  return pageMetadata(lang, "/challenger", t.title, t.intro);
}

export default async function Challenger({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).challenger;
  const progress = await shadowProgress();

  return (
    <>
      <Page title={t.title} intro={t.intro}>
        <Card>
          <h2 className="font-bold">{t.criteria}</h2>
          <ol className="mt-2 list-decimal space-y-1 pl-5 leading-relaxed">
            <li>{t.c1}</li>
            <li>{t.c2}</li>
            <li>{t.c3}</li>
          </ol>
          <a className="mt-3 inline-block underline" href={`${REPO}/blob/main/reports/preregistration_e4a.md`}>
            {t.prereg}
          </a>
        </Card>
        <Section title={t.progress}>
          <Table
            head={["", t.weeks, t.moves, t.predictions, t.verdict]}
            rows={progress.map((p) => [
              cropName(lang, p.crop),
              `${(p.days_covered / 7).toFixed(1)} / 12`,
              `${p.n_moves} / 30`,
              p.n_evaluated,
              p.verdict,
            ])}
          />
        </Section>
      </Page>
    </>
  );
}
