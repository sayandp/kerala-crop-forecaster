import { notFound } from "next/navigation";
import { Footer, Nav } from "@/components/Nav";
import { SeriesDetail, cropName, seriesPath } from "@/components/SeriesDetail";
import { Page } from "@/components/ui";
import { dict, LANGS } from "@/lib/i18n";
import { pageMetadata, resolveLang } from "@/lib/page";
import { overview, seriesList, seriesView } from "@/lib/queries";

export const revalidate = 3600;

type Params = { params: Promise<{ lang: string; crop: string; market: string }> };

export async function generateStaticParams() {
  const series = await seriesList();
  return LANGS.flatMap((lang) => series.map((s) => ({ lang, crop: s.commodity, market: s.market })));
}

async function resolve(params: Params["params"]) {
  const lang = await resolveLang(params);
  const { crop, market } = await params;
  return { lang, crop: decodeURIComponent(crop), market: decodeURIComponent(market) };
}

export async function generateMetadata({ params }: Params) {
  const { lang, crop, market } = await resolve(params);
  const t = dict(lang);
  const title = `${cropName(lang, crop)} · ${market}`;
  return pageMetadata(lang, seriesPath(crop, market), title, `${t.prices.range7}: ${title}`);
}

export default async function SeriesPage({ params }: Params) {
  const { lang, crop, market } = await resolve(params);
  const [view, all] = await Promise.all([seriesView(crop, market), overview()]);
  if (!view) notFound();
  return (
    <>
      <Nav lang={lang} path={seriesPath(crop, market)} />
      <Page title={`${cropName(lang, crop)} · ${market}`}>
        <SeriesDetail lang={lang} view={view} all={all} />
      </Page>
      <Footer lang={lang} />
    </>
  );
}
