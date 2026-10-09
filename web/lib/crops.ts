import { dict, type Lang } from "@/lib/i18n";

/**
 * Product keys shown to people. One commodity can hold several products (banana varieties,
 * big vs small onion), so a crop = commodity + optional variety filter. Mirrors
 * config/series.yaml (`crop:`) and config/aliases.yaml (`crops:`, same order).
 * `ref` = the headline market (first market of config/channel.yaml).
 */
export type Group = "cash" | "banana" | "veg";

interface CropDef {
  key: string;
  commodity: string;
  varieties?: readonly string[];
  group: Group;
  ref: string;
}

export const CROP_DEFS = [
  { key: "coconut", commodity: "coconut", group: "cash", ref: "Koduvayoor" },
  { key: "pepper", commodity: "pepper", group: "cash", ref: "Kannur" },
  { key: "rubber", commodity: "rubber", group: "cash", ref: "Kalpetta" },
  { key: "arecanut", commodity: "arecanut", group: "cash", ref: "Manjeswaram" },
  { key: "coffee", commodity: "coffee", group: "cash", ref: "Kalpetta" },
  { key: "ginger", commodity: "ginger", group: "cash", ref: "Kayamkulam" },
  { key: "banana", commodity: "banana", varieties: ["Nendran"], group: "banana", ref: "Kayamkulam" },
  { key: "palayankodan", commodity: "banana", varieties: ["Palayamthodan"], group: "banana", ref: "Kayamkulam" },
  { key: "poovan", commodity: "banana", varieties: ["Poovan"], group: "banana", ref: "Palakkad" },
  { key: "tapioca", commodity: "tapioca", group: "veg", ref: "Payyannur" },
  { key: "tomato", commodity: "tomato", group: "veg", ref: "Kayamkulam" },
  { key: "onion", commodity: "onion", varieties: ["Big"], group: "veg", ref: "Kayamkulam" },
  { key: "small_onion", commodity: "onion", varieties: ["Small"], group: "veg", ref: "Kayamkulam" },
  { key: "green_chilli", commodity: "green_chilli", group: "veg", ref: "Kayamkulam" },
  { key: "bitter_gourd", commodity: "bitter_gourd", group: "veg", ref: "Manjeswaram" },
  { key: "drumstick", commodity: "drumstick", group: "veg", ref: "Kayamkulam" },
  { key: "cucumber", commodity: "cucumber", group: "veg", ref: "Payyannur" },
] as const satisfies readonly CropDef[];

export type Crop = (typeof CROP_DEFS)[number]["key"];
export const CROPS: readonly Crop[] = CROP_DEFS.map((d) => d.key);
export const GROUPS: readonly Group[] = ["cash", "banana", "veg"];

const BY_KEY = new Map<string, CropDef>(CROP_DEFS.map((d) => [d.key, d]));

export function isCrop(v: string): v is Crop {
  return BY_KEY.has(v);
}

export function cropDef(crop: Crop): CropDef {
  return BY_KEY.get(crop) as CropDef;
}

/** Product key of a stored series (commodity + variety), or null if it is not served. */
export function cropOf(row: { commodity: string; variety: string }): Crop | null {
  for (const d of CROP_DEFS as readonly CropDef[]) {
    if (d.commodity !== row.commodity) continue;
    if (!d.varieties || d.varieties.includes(row.variety)) return d.key as Crop;
  }
  return null;
}

export function refMarket(crop: Crop): string {
  return cropDef(crop).ref;
}

/** Malayalam market names (config/aliases.yaml: first Malayalam name). */
const ML_MARKET: Record<string, string> = {
  Kayamkulam: "കായംകുളം",
  "Chenkal VFPCK": "ചെങ്കൽ",
  "Mookkannur VFPCK": "മൂക്കന്നൂർ",
  Parassala: "പാറശ്ശാല",
  "Thiruvaniyoor VFPCK": "തിരുവാണിയൂർ",
  "Elamad VFPCK": "ഇളമാട്",
  "Kunnukara VFPCK": "കുന്നുകര",
  "Vengannore VFPCK": "വെങ്ങാനൂർ",
  Koduvayoor: "കൊടുവായൂർ",
  Palakkad: "പാലക്കാട്",
  "North Paravur": "വടക്കൻ പറവൂർ",
  Kannur: "കണ്ണൂർ",
  Manjeswaram: "മഞ്ചേശ്വരം",
  Payyannur: "പയ്യന്നൂർ",
  Perumbavoor: "പെരുമ്പാവൂർ",
  Pulpally: "പുൽപ്പള്ളി",
  Kalpetta: "കൽപ്പറ്റ",
};

const ML_DISTRICT: Record<string, string> = {
  Thiruvananthapuram: "തിരുവനന്തപുരം",
  Kollam: "കൊല്ലം",
  Pathanamthitta: "പത്തനംതിട്ട",
  Alappuzha: "ആലപ്പുഴ",
  Kottayam: "കോട്ടയം",
  Idukki: "ഇടുക്കി",
  Ernakulam: "എറണാകുളം",
  Thrissur: "തൃശ്ശൂർ",
  Palakkad: "പാലക്കാട്",
  Malappuram: "മലപ്പുറം",
  Kozhikode: "കോഴിക്കോട്",
  Wayanad: "വയനാട്",
  Kannur: "കണ്ണൂർ",
  Kasaragod: "കാസർകോട്",
};

export function marketName(market: string, lang: Lang): string {
  if (lang === "ml") return ML_MARKET[market] ?? market;
  return market.replace(/ VFPCK$/, "");
}

export function districtName(district: string, lang: Lang): string {
  return lang === "ml" ? (ML_DISTRICT[district] ?? district) : district;
}

/** Telegram deep link: /start alert_<crop>_<market-slug> (handled in cropcast.bot.handlers). */
export const BOT = "keralacropprices_bot";

export function marketSlug(market: string): string {
  return market
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function botAlertLink(crop: string, market?: string): string {
  const payload = market ? `alert_${crop}_${marketSlug(market)}` : `alert_${crop}`;
  return `https://t.me/${BOT}?start=${payload}`;
}

export function cropName(lang: Lang, crop: string): string {
  const crops = dict(lang).crops as Record<string, string>;
  return crops[crop] ?? crop;
}
