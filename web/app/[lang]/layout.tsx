import type { Metadata, Viewport } from "next";
import { Noto_Sans_Malayalam } from "next/font/google";
import type { ReactNode } from "react";
import "../globals.css";
import { dict } from "@/lib/i18n";
import { SITE_URL, langStaticParams, resolveLang, type LangParams } from "@/lib/page";

const noto = Noto_Sans_Malayalam({
  // One variable font file per subset serves both weights. Only the Malayalam file is preloaded
  // (`subsets`); the Latin files are still declared and load on demand (market names, digits).
  subsets: ["malayalam"],
  weight: ["400", "700"],
  // swap: text paints at once in the fallback. Measured 2026-10-09 (local, 3 runs each): same
  // simulated LCP as "optional" (2.71 s) but first paint on a cold start 1.2 s vs 2.2 s.
  display: "swap",
  variable: "--font-malayalam",
});

export const dynamicParams = false;
export const generateStaticParams = langStaticParams;

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fcfcfb" },
    { media: "(prefers-color-scheme: dark)", color: "#141413" },
  ],
};

export async function generateMetadata({ params }: LangParams): Promise<Metadata> {
  const lang = await resolveLang(params);
  const t = dict(lang);
  return {
    metadataBase: new URL(SITE_URL),
    title: t.site.title,
    description: t.site.tagline,
    applicationName: "cropcast",
  };
}

export default async function RootLayout({ children, params }: LangParams & { children: ReactNode }) {
  const lang = await resolveLang(params);
  return (
    <html lang={lang} className={noto.variable}>
      <body className="min-h-dvh font-sans antialiased">{children}</body>
    </html>
  );
}
