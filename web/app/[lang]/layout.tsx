import type { Metadata, Viewport } from "next";
import { Noto_Sans_Malayalam } from "next/font/google";
import type { ReactNode } from "react";
import "../globals.css";
import { Chrome } from "@/components/Chrome";
import { dict } from "@/lib/i18n";
import { SITE_URL, langStaticParams, resolveLang, type LangParams } from "@/lib/page";

const noto = Noto_Sans_Malayalam({
  // One variable font file per subset serves both weights. Only the Malayalam file is preloaded
  // (`subsets`); Latin text uses the system UI font (-apple-system / system-ui / Roboto).
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
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#e8f0e1" },
    { media: "(prefers-color-scheme: dark)", color: "#0d1511" },
  ],
};

export async function generateMetadata({ params }: LangParams): Promise<Metadata> {
  const lang = await resolveLang(params);
  const t = dict(lang);
  return {
    metadataBase: new URL(SITE_URL),
    title: t.site.title,
    description: t.site.tagline,
    applicationName: t.site.title,
    manifest: "/manifest.webmanifest",
    appleWebApp: { capable: true, title: t.site.title, statusBarStyle: "default" },
    icons: {
      icon: [{ url: "/favicon.ico" }, { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
      apple: "/icons/apple-touch-icon.png",
    },
  };
}

export default async function RootLayout({ children, params }: LangParams & { children: ReactNode }) {
  const lang = await resolveLang(params);
  const t = dict(lang);
  return (
    <html lang={lang} className={noto.variable}>
      <body className="min-h-dvh font-sans antialiased">
        <div className="app-backdrop" aria-hidden="true" />
        <Chrome lang={lang} t={{ nav: t.nav, site: t.site }} />
        <div className="pb-28 md:pb-10">{children}</div>
        <footer className="mx-auto max-w-5xl px-4 pb-32 text-[13px] text-ink-2 md:pb-10">
          <p>
            {t.common.updated} · Agmarknet ·{" "}
            <a className="underline underline-offset-4" href="https://github.com/sayandp/kerala-crop-forecaster">
              {t.common.repo}
            </a>
          </p>
        </footer>
      </body>
    </html>
  );
}
