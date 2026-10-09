import { CROPS, REF_MARKET, isCrop, type Crop } from "@/lib/crops";
import { shortDate } from "@/lib/format";
import { dict } from "@/lib/i18n";
import { cropOgImage, ogContentType, ogImage, ogSize } from "@/lib/og";
import { latestAll } from "@/lib/queries";
import { kg } from "@/lib/view";

export const size = ogSize;
export const contentType = ogContentType;
export const alt = "Kerala market price card";
export const revalidate = 3600;

export function generateStaticParams(): { crop: string }[] {
  return CROPS.map((crop) => ({ crop }));
}

export default async function Image({ params }: { params: Promise<{ crop: string }> }) {
  const { crop } = await params;
  if (!isCrop(crop)) return ogImage("Kerala market prices", "Daily mandi prices");
  const row = (await latestAll()).find((r) => r.commodity === crop && r.market === REF_MARKET[crop as Crop]);
  const en = dict("en").crops[crop];
  if (!row) return ogImage(en, "Kerala market prices");
  return cropOgImage({
    crop,
    cropEn: en,
    market: row.market,
    price: row.p === null ? null : kg(row.p),
    lo: kg(row.p10),
    hi: kg(row.p90),
    date: row.d ? shortDate(row.d, "en") : "",
  });
}
