import { CropCard } from "@/components/CropCard";
import { Chip, LargeTitle } from "@/components/glass";
import { cropPath } from "@/components/CropPage";
import { CROPS, GROUPS, cropDef, cropName, cropOf, marketName } from "@/lib/crops";
import { dict, href } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";
import { latestAll, sparklines } from "@/lib/queries";
import { cropCards, isFresh, refSeries } from "@/lib/view";

export const revalidate = 3600;
export const generateStaticParams = langStaticParams;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang);
  return pageMetadata(lang, "/crops", t.cropsPage.title, t.cropsPage.lead);
}

export default async function Crops({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang);
  const latest = await latestAll();
  const cards = cropCards(latest, await sparklines(refSeries(latest)));

  return (
    <main id="main" className="mx-auto max-w-5xl px-4 pt-6">
      <LargeTitle title={t.cropsPage.title} lead={t.cropsPage.lead} />
      <div className="space-y-8">
        {GROUPS.map((g) => (
          <section key={g} aria-labelledby={`group-${g}`}>
            <h2 id={`group-${g}`} className="mb-3 text-[20px] font-bold">
              {t.groups[g]}
            </h2>
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {cards
                .filter((c) => cropDef(c.crop).group === g)
                .map((c) => (
                  <CropCard key={c.crop} lang={lang} c={c} />
                ))}
            </ul>
          </section>
        ))}
      </div>
      <h2 className="mt-10 mb-3 text-[20px] font-bold">{t.crop.markets}</h2>
      <div className="space-y-5">
        {CROPS.map((crop) => {
          const markets = latest.filter((r) => cropOf(r) === crop);
          if (markets.length === 0) return null;
          return (
            <section key={crop} aria-label={cropName(lang, crop)}>
              <h3 className="mb-2 font-bold">{cropName(lang, crop)}</h3>
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
