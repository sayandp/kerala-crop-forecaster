import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { dict, href, isLang, LANGS, type Lang } from "@/lib/i18n";

export type LangParams = { params: Promise<{ lang: string }> };

export const SITE_URL = process.env.VERCEL_PROJECT_PRODUCTION_URL
  ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
  : "https://kerala-crop-forecaster.vercel.app";

export function langStaticParams(): { lang: Lang }[] {
  return LANGS.map((lang) => ({ lang }));
}

export async function resolveLang(params: Promise<{ lang: string }>): Promise<Lang> {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  return lang;
}

/** Title, description, canonical + hreflang alternates for a logical path ("/accuracy"). */
export function pageMetadata(lang: Lang, path: string, title: string, description: string): Metadata {
  const site = dict(lang).site.title;
  return {
    title: path === "/" ? site : `${title} · ${site}`,
    description,
    alternates: {
      canonical: href(lang, path),
      languages: { ml: href("ml", path), en: href("en", path) },
    },
    openGraph: { title, description, type: "website", locale: lang === "ml" ? "ml_IN" : "en_IN" },
    twitter: { card: "summary_large_image", title, description },
  };
}
