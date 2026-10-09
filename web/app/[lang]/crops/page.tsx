import { CropCard } from "@/components/CropCard";
import { Chip, LargeTitle } from "@/components/glass";
import { cropPath } from "@/components/CropPage";
import { CROPS, REF_MARKET, cropName, marketName } from "@/lib/crops";
import { dict, href } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";
import { latestAll, sparklines } from "@/lib/queries";
import { cropCards, isFresh } from "@/lib/view";

export const revalidate = 3600;
export const generateStaticParams = langStaticParams;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang);
  return pageMetadata(lang, "/crops", t.crops.title, t.crops.lead);
}

export default async function Crops({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang);
  const latest = await latestAll();
  const refs = latest.filter((r) => REF_MARKET[r.commodity as keyof typeof REF_MARKET] === r.market);
  const cards = cropCards(latest, await sparklines(refs));

  return (
    <main id="main" className="mx-auto max-w-5xl px-4 pt-6">
      <LargeTitle title={t.crops.title} lead={t.crops.lead} />
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((c) => (
          <CropCard key={c.crop} lang={lang} c={c} />
        ))}
      </ul>
      <div className="mt-8 space-y-5">
        {CROPS.map((crop) => {
          const markets = latest.filter((r) => r.commodity === crop);
          if (markets.length === 0) return null;
          return (
            <section key={crop} aria-label={cropName(lang, crop)}>
              <h2 className="mb-2 font-bold">{cropName(lang, crop)}</h2>
              <ul className="flex flex-wrap gap-2">
                {markets.map((r) => (
                  <li key={r.market}>
                    <Chip href={href(lang, cropPath(crop, r.market))}>
                      {marketName(r.market, lang)}
                      {!isFresh(r) && <span className="text-[12px] font-normal text-warn">· {t.crop.stale}</span>}
                    </Chip>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </main>
  );
}
