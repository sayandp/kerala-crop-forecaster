import en from "@/i18n/en.json";
import ml from "@/i18n/ml.json";

export const LANGS = ["ml", "en"] as const;
export type Lang = (typeof LANGS)[number];
export type Dict = typeof en;

const DICTS: Record<Lang, Dict> = { ml, en };

export function isLang(v: string): v is Lang {
  return (LANGS as readonly string[]).includes(v);
}

export function dict(lang: Lang): Dict {
  return DICTS[lang];
}

/** Path for `lang`: Malayalam (default) at clean URLs, English under /en. */
export function href(lang: Lang, path: string): string {
  if (lang === "ml") return path;
  return path === "/" ? "/en" : `/en${path}`;
}

/** The same page in the other language. `path` is the logical path ("/", "/accuracy"). */
export function otherLang(lang: Lang): Lang {
  return lang === "ml" ? "en" : "ml";
}

export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, k: string) => String(values[k] ?? ""));
}
