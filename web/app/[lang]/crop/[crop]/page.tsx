import { CropPage, cropPath } from "@/components/CropPage";
import { CROPS, cropName, isCrop } from "@/lib/crops";
import { dict } from "@/lib/i18n";
import { pageMetadata, resolveLang } from "@/lib/page";

export const revalidate = 3600;

type Params = { params: Promise<{ lang: string; crop: string }> };

export function generateStaticParams(): { crop: string }[] {
  return CROPS.map((crop) => ({ crop }));
}

export async function generateMetadata({ params }: Params) {
  const { crop } = await params;
  const lang = await resolveLang(params);
  const t = dict(lang);
  const name = isCrop(crop) ? cropName(lang, crop) : crop;
  return pageMetadata(lang, cropPath(crop), name, `${name}: ${t.crop.range7}. ${t.home.lead}`);
}

export default async function Crop({ params }: Params) {
  const { crop } = await params;
  const lang = await resolveLang(params);
  return <CropPage lang={lang} crop={crop} />;
}
