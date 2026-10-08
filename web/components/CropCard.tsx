import Link from "next/link";
import { CropIcon } from "@/components/CropIcon";
import { PriceBadge, TrendPill } from "@/components/glass";
import { MiniSpark } from "@/components/MiniSpark";
import { cropName, marketName } from "@/lib/crops";
import { shortDate } from "@/lib/format";
import { dict, href, type Lang } from "@/lib/i18n";
import type { CropCardData } from "@/lib/view";

/** Home / Crops tile: the whole card is one link (one tap target, one accessible name). */
export function CropCard({ lang, c }: { lang: Lang; c: CropCardData }) {
  const t = dict(lang);
  const name = cropName(lang, c.crop);
  return (
    <li>
      <Link
        href={href(lang, `/crop/${c.crop}`)}
        prefetch={false}
        className="press surface-glass flex h-full flex-col gap-3 p-4 hover:shadow-lg focus-visible:outline-2 focus-visible:outline-accent"
      >
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-[14px] bg-accent-soft text-accent">
            <CropIcon crop={c.crop} />
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-[17px] leading-snug font-bold">{name}</h2>
            <p className="truncate text-[13px] text-ink-2">{marketName(c.market, lang)}</p>
          </div>
        </div>
        {c.price === null ? (
          <p className="text-ink-2">{t.home.noData}</p>
        ) : (
          <>
            <div className="flex flex-wrap items-end justify-between gap-2">
              <PriceBadge value={`₹${c.price}`} unit={t.prices.perKg} />
              <TrendPill pct={c.change} label={t.home.vs7} />
            </div>
            <MiniSpark values={c.spark} />
            <p className="text-[13px] text-ink-2">
              {t.home.updated} {c.date ? shortDate(c.date, lang) : "–"}
              {!c.fresh && <span className="ml-2 font-semibold text-warn">⚠ {t.crop.stale}</span>}
            </p>
            {c.best && (
              <p className="surface-data !rounded-[14px] px-3 py-2 text-[14px]">
                <span className="text-ink-2">{t.home.best}: </span>
                <span className="font-semibold">
                  {marketName(c.best.market, lang)} ₹{c.best.price}
                </span>
              </p>
            )}
          </>
        )}
      </Link>
    </li>
  );
}
