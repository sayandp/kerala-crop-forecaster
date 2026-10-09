import { CropIcon } from "@/components/CropIcon";
import { Chip, DataCard, GlassCard, LargeTitle } from "@/components/glass";
import { BOT, CROPS, botAlertLink, cropName, cropOf, marketName } from "@/lib/crops";
import { TELEGRAM_CHANNEL } from "@/lib/format";
import { dict } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";
import { latestAll } from "@/lib/queries";

export const revalidate = 3600;
export const generateStaticParams = langStaticParams;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).alertsPage;
  return pageMetadata(lang, "/alerts", t.title, t.lead);
}

export default async function Alerts({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang);
  const a = t.alertsPage;
  const latest = await latestAll();

  return (
    <main id="main" className="mx-auto max-w-5xl px-4 pt-6">
      <LargeTitle title={a.title} lead={a.lead} />
      <div className="flex flex-wrap gap-3">
        <a
          href={`https://t.me/${BOT}`}
          target="_blank"
          rel="noopener noreferrer"
          className="press inline-flex min-h-12 items-center rounded-full bg-accent px-6 text-[16px] font-semibold text-accent-ink"
        >
          {a.open} @{BOT}
        </a>
        <Chip href={TELEGRAM_CHANNEL} external>
          {a.channel}
        </Chip>
      </div>

      <h2 className="mt-8 mb-3 text-lg font-bold">{a.pick}</h2>
      <ul className="grid gap-4 md:grid-cols-2">
        {CROPS.map((crop) => (
          <GlassCard as="li" key={crop}>
            <h3 className="mb-3 flex items-center gap-2 font-bold">
              <span className="grid h-9 w-9 place-items-center rounded-[12px] bg-accent-soft text-accent">
                <CropIcon crop={crop} className="h-6 w-6" />
              </span>
              {cropName(lang, crop)}
            </h3>
            <ul className="flex flex-wrap gap-2">
              {latest
                .filter((r) => cropOf(r) === crop)
                .map((r) => (
                  <li key={r.market}>
                    <Chip href={botAlertLink(crop, r.market)} external>
                      🔔 {marketName(r.market, lang)}
                    </Chip>
                  </li>
                ))}
            </ul>
          </GlassCard>
        ))}
      </ul>
      <DataCard className="mt-6">
        <p className="text-[14px] leading-relaxed text-ink-2">{a.privacy}</p>
      </DataCard>
    </main>
  );
}
