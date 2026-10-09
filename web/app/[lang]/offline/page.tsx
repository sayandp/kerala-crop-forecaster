import Link from "next/link";
import { DataCard, LargeTitle } from "@/components/glass";
import { dict, href } from "@/lib/i18n";
import { langStaticParams, resolveLang, type LangParams } from "@/lib/page";

// Static (no database): the service worker precaches it and serves it when a page is not cached.
export const dynamic = "force-static";
export const generateStaticParams = langStaticParams;

export async function generateMetadata({ params }: LangParams) {
  const lang = await resolveLang(params);
  return { title: dict(lang).offline.title, robots: { index: false } };
}

export default async function Offline({ params }: LangParams) {
  const lang = await resolveLang(params);
  const t = dict(lang).offline;
  return (
    <main id="main" className="mx-auto max-w-xl px-4 pt-10">
      <LargeTitle title={t.title} lead={t.lead} />
      <DataCard>
        <Link
          href={href(lang, "/")}
          className="press inline-flex min-h-12 items-center rounded-full bg-accent px-6 font-semibold text-accent-ink"
        >
          {t.retry}
        </Link>
      </DataCard>
    </main>
  );
}
