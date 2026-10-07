import type { Lang } from "@/lib/i18n";

/** Agmarknet prices are Rs./quintal; farmers think in Rs./kg. */
export function perKg(rsPerQuintal: number): number {
  return rsPerQuintal / 100;
}

export function rupees(rsPerQuintal: number): string {
  const kg = perKg(rsPerQuintal);
  return `₹${kg >= 100 ? kg.toFixed(0) : kg.toFixed(kg >= 10 ? 0 : 1)}`;
}

export function shortDate(iso: string, lang: Lang): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString(lang === "ml" ? "ml-IN" : "en-IN", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);
}

export const STALE_DAYS = 3;

export const REPO = "https://github.com/sayandp/kerala-crop-forecaster";
export const TELEGRAM_CHANNEL = process.env.NEXT_PUBLIC_TELEGRAM_CHANNEL_URL ?? "https://t.me/";
export const DAGSHUB = "https://dagshub.com/sayandp/kerala-crop-forecaster";
