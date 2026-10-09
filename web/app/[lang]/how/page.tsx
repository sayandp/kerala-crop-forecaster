import Link from "next/link";
import { LargeTitle } from "@/components/glass";
import { dict, href } from "@/lib/i18n";
import { langStaticParams, pageMetadata, resolveLang, type LangParams } from "@/lib/page";

export const revalidate = 3600;
export const generateStaticParams = langStaticParams;

const PAGES = ["accuracy", "models", "challenger", "drift", "health"] as const;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).how;
  return pageMetadata(lang, "/how", t.title, t.lead);
}

export default async function How({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang);
  return (
    <main id="main" className="mx-auto max-w-5xl px-4 pt-6">
      <LargeTitle title={t.how.title} lead={t.how.lead} />
      <ul className="grid gap-3 md:grid-cols-2">
        {PAGES.map((p) => (
          <li key={p}>
            <Link
              href={href(lang, `/${p}`)}
              prefetch={false}
              className="press surface-glass flex min-h-20 items-center justify-between gap-3 p-4 hover:shadow-lg"
            >
              <span>
                <span className="block text-[17px] font-bold">{t.nav[p]}</span>
                <span className="block text-[14px] text-ink-2">{t.how[p]}</span>
              </span>
              <span aria-hidden="true" className="text-xl text-ink-2">
                ›
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
