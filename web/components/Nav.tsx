import Link from "next/link";
import { dict, href, otherLang, type Lang } from "@/lib/i18n";

const PAGES = [
  ["prices", "/"],
  ["accuracy", "/accuracy"],
  ["models", "/models"],
  ["challenger", "/challenger"],
  ["drift", "/drift"],
  ["health", "/health"],
] as const;

export function Nav({ lang, path }: { lang: Lang; path: string }) {
  const t = dict(lang);
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 pt-4">
        <Link href={href(lang, "/")} className="text-lg font-bold">
          {t.site.title}
        </Link>
        <Link
          href={href(otherLang(lang), path)}
          hrefLang={otherLang(lang)}
          className="rounded-full border border-line px-3 py-1.5 text-sm"
        >
          {t.nav.lang}
        </Link>
      </div>
      <nav aria-label="Main" className="mx-auto max-w-3xl overflow-x-auto px-4">
        <ul className="flex gap-1 py-2 text-sm whitespace-nowrap">
          {PAGES.map(([key, p]) => {
            const active = p === "/" ? path === "/" || path.startsWith("/p/") : path === p;
            return (
              <li key={key}>
                <Link
                  href={href(lang, p)}
                  aria-current={active ? "page" : undefined}
                  className={`block rounded-md px-3 py-2 ${active ? "bg-ink text-paper" : "text-muted"}`}
                >
                  {t.nav[key]}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}

export function Footer({ lang }: { lang: Lang }) {
  const t = dict(lang);
  return (
    <footer className="mx-auto mt-12 max-w-3xl border-t border-line px-4 py-6 text-sm text-muted">
      <p>
        {t.common.updated} ·{" "}
        <a className="underline" href="https://github.com/sayandp/kerala-crop-forecaster">
          {t.common.repo}
        </a>
      </p>
    </footer>
  );
}
