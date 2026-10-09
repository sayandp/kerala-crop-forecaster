import { CropCard } from "@/components/CropCard";
import { LargeTitle } from "@/components/glass";
import { InstallPrompt } from "@/components/InstallPrompt";
import { GROUPS, cropDef } from "@/lib/crops";
import { dict } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";
import { latestAll, sparklines } from "@/lib/queries";
import { cropCards, refSeries } from "@/lib/view";

export const revalidate = 3600;
export const generateStaticParams = langStaticParams;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang);
  return pageMetadata(lang, "/", t.home.title, t.site.tagline);
}

export default async function Home({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang);
  const latest = await latestAll();
  const cards = cropCards(latest, await sparklines(refSeries(latest)));

  return (
    <main id="main" className="mx-auto max-w-5xl px-4 pt-6">
      <LargeTitle title={t.home.title} lead={t.home.lead} />
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
      <p className="mt-6 max-w-2xl text-[13px] text-ink-2">{t.crop.rangeNote}</p>
      <InstallPrompt label={t.home.install} iosHint={t.home.installIos} close={t.crop.close} />
    </main>
  );
}
