"use client";

// App chrome: glass top bar (brand, desktop nav, language) and the floating glass tab bar on
// mobile. These are the only always-on blurred layers (2); an open sheet is the 3rd.
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { href, otherLang, type Dict, type Lang } from "@/lib/i18n";

type Tab = "home" | "crops" | "alerts" | "how";

const TABS: { key: Tab; path: string; match: RegExp; icon: ReactNode }[] = [
  {
    key: "home",
    path: "/",
    match: /^\/$/,
    icon: <path d="M4 11.2 12 4.5l8 6.7V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1v-7.8Z" />,
  },
  {
    key: "crops",
    path: "/crops",
    match: /^\/crops?(\/|$)/,
    icon: (
      <>
        <path d="M12 20v-8" />
        <path d="M12 12c0-3.9 2.7-6.7 7-7-0.3 4.3-3.1 7-7 7ZM12 14c0-3.3-2.3-5.7-6-6 .3 3.7 2.7 6 6 6Z" />
      </>
    ),
  },
  {
    key: "alerts",
    path: "/alerts",
    match: /^\/alerts(\/|$)/,
    icon: (
      <>
        <path d="M6.5 16.5V11a5.5 5.5 0 1 1 11 0v5.5l1.5 1.5H5l1.5-1.5Z" />
        <path d="M10 20.2a2.2 2.2 0 0 0 4 0" />
      </>
    ),
  },
  {
    key: "how",
    path: "/how",
    match: /^\/(how|accuracy|models|challenger|drift|health)(\/|$)/,
    icon: (
      <>
        <circle cx="12" cy="12" r="8" />
        <path d="M12 11v5M12 8h.01" />
      </>
    ),
  },
];

function logicalPath(pathname: string): string {
  const p = pathname.replace(/^\/(ml|en)(?=\/|$)/, "");
  return p === "" ? "/" : p;
}

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-6 w-6"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function Chrome({ lang, t }: { lang: Lang; t: Pick<Dict, "nav" | "site"> }) {
  const path = logicalPath(usePathname() ?? "/");
  const other = otherLang(lang);
  const active = TABS.find((tab) => tab.match.test(path))?.key;

  return (
    <>
      <a href="#main" className="sr-only-focusable fixed top-2 left-2 z-50 rounded-lg bg-accent px-3 py-2 text-accent-ink">
        {t.nav.skip}
      </a>
      <header className="sticky top-0 z-40 px-3 pt-[max(env(safe-area-inset-top),8px)]">
        <div className="glass glass-thick mx-auto flex max-w-5xl items-center justify-between gap-3 rounded-[22px] px-4 py-2">
          <Link href={href(lang, "/")} className="flex min-h-11 items-center gap-2 font-bold" prefetch={false}>
            <span aria-hidden="true" className="grid h-8 w-8 place-items-center rounded-[10px] bg-accent text-accent-ink">
              <Icon>
                <path d="M12 20v-8M12 12c0-3.9 2.7-6.7 7-7-.3 4.3-3.1 7-7 7ZM12 14c0-3.3-2.3-5.7-6-6 .3 3.7 2.7 6 6 6Z" />
              </Icon>
            </span>
            <span className="text-[17px]">{t.site.title}</span>
          </Link>
          <nav aria-label="Main" className="hidden md:block">
            <ul className="flex items-center gap-1">
              {TABS.map((tab) => (
                <li key={tab.key}>
                  <Link
                    href={href(lang, tab.path)}
                    aria-current={active === tab.key ? "page" : undefined}
                    prefetch={false}
                    className={`press flex min-h-11 items-center rounded-full px-4 text-[15px] font-semibold ${
                      active === tab.key ? "bg-accent text-accent-ink" : "text-ink-2 hover:bg-line"
                    }`}
                  >
                    {t.nav[tab.key]}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <Link
            href={href(other, path)}
            hrefLang={other}
            lang={other}
            prefetch={false}
            className="press flex min-h-11 items-center rounded-full border border-line px-4 text-[15px] font-semibold"
          >
            {t.nav.lang}
          </Link>
        </div>
      </header>

      <nav
        aria-label="Tabs"
        className="fixed inset-x-0 bottom-0 z-40 px-3 pb-[max(env(safe-area-inset-bottom),10px)] md:hidden"
      >
        <ul className="glass glass-thick mx-auto grid max-w-md grid-cols-4 rounded-[26px] p-1.5">
          {TABS.map((tab) => {
            const on = active === tab.key;
            return (
              <li key={tab.key}>
                <Link
                  href={href(lang, tab.path)}
                  aria-current={on ? "page" : undefined}
                  prefetch={false}
                  className={`press flex min-h-14 flex-col items-center justify-center gap-0.5 rounded-[20px] text-[12px] leading-tight font-semibold ${
                    on ? "bg-accent text-accent-ink" : "text-ink"
                  }`}
                >
                  <Icon>{tab.icon}</Icon>
                  <span className="max-w-full truncate px-1">{t.nav[tab.key]}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
