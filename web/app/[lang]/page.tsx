import Link from "next/link";
import { Footer, Nav } from "@/components/Nav";
import { SeriesDetail, cropName, seriesPath } from "@/components/SeriesDetail";
import { Page, Section, Table } from "@/components/ui";
import { STALE_DAYS, daysBetween, rupees } from "@/lib/format";
import { dict, href } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";
import { overview, seriesView } from "@/lib/queries";

export const revalidate = 3600;
export const generateStaticParams = langStaticParams;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang);
  return pageMetadata(lang, "/", t.site.title, t.site.tagline);
}

export default async function Home({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang);
  const all = await overview();
  // Default series: the freshest one (ties: first alphabetically).
  const fresh = all.filter((o) => o.last_observed && daysBetween(o.last_observed, o.as_of) <= STALE_DAYS);
  const pick = fresh[0] ?? all[0];
  const view = pick ? await seriesView(pick.commodity, pick.market) : null;

  return (
    <>
      <Nav lang={lang} path="/" />
      <Page title={t.site.title} intro={t.site.tagline}>
        <SeriesDetail lang={lang} view={view} all={all} />
        {all.length > 0 && (
          <Section title={t.prices.range7}>
            <Table
              head={[t.prices.pick, t.prices.latest, t.prices.range7]}
              rows={all.map((o) => {
                const stale = !o.last_observed || daysBetween(o.last_observed, o.as_of) > STALE_DAYS;
                return [
                  <Link
                    key="l"
                    className="underline"
                    href={href(lang, seriesPath(o.commodity, o.market))}
                    prefetch={false}
                  >
                    {cropName(lang, o.commodity)} · {o.market}
                  </Link>,
                  <span key="p" className={stale ? "text-muted" : ""}>
                    {o.last_value !== null ? rupees(o.last_value) : "–"}
                    {stale ? " *" : ""}
                  </span>,
                  `${rupees(o.p10)}–${rupees(o.p90).slice(1)}`,
                ];
              })}
            />
            <p className="mt-2 text-xs text-muted">* {t.prices.stale}</p>
          </Section>
        )}
      </Page>
      <Footer lang={lang} />
    </>
  );
}
