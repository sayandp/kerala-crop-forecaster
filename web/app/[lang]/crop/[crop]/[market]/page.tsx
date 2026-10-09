import { CropPage, cropPath } from "@/components/CropPage";
import { cropName, cropOf, isCrop, marketName } from "@/lib/crops";
import { dict } from "@/lib/i18n";
import { pageMetadata, resolveLang } from "@/lib/page";
import { latestAll } from "@/lib/queries";

export const revalidate = 3600;

type Params = { params: Promise<{ lang: string; crop: string; market: string }> };

/** Every served market is prebuilt (ISR); crop + market come from here (the parent [crop]
 * page's params do not propagate to child segments). Unknown pairs render on demand and 404. */
export async function generateStaticParams(): Promise<{ crop: string; market: string }[]> {
  const rows = await latestAll();
  return rows.flatMap((r) => {
    const crop = cropOf(r);
    return crop ? [{ crop, market: r.market }] : [];
  });
}

export async function generateMetadata({ params }: Params) {
  const { crop, market } = await params;
  const lang = await resolveLang(params);
  const m = decodeURIComponent(market);
  const name = isCrop(crop) ? cropName(lang, crop) : crop;
  const title = `${name} · ${marketName(m, lang)}`;
  return pageMetadata(lang, cropPath(crop, m), title, `${title}: ${dict(lang).crop.range7}.`);
}

export default async function CropMarket({ params }: Params) {
  const { crop, market } = await params;
  const lang = await resolveLang(params);
  return <CropPage lang={lang} crop={crop} market={decodeURIComponent(market)} />;
}
