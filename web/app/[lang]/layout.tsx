import type { Metadata, Viewport } from "next";
import { Noto_Sans_Malayalam } from "next/font/google";
import type { ReactNode } from "react";
import "../globals.css";
import { dict } from "@/lib/i18n";
import { SITE_URL, langStaticParams, resolveLang, type LangParams } from "@/lib/page";

const noto = Noto_Sans_Malayalam({
  subsets: ["malayalam", "latin"],
  weight: ["400", "700"],
  // "optional": no late swap repaint (it delayed LCP by ~2.5 s on mobile). Android ships Noto Sans
  // Malayalam as the system font, so a first visit on a slow network still renders Malayalam well.
  display: "optional",
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
