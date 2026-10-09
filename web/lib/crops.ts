import { dict, type Lang } from "@/lib/i18n";

export const CROPS = ["banana", "coconut", "pepper", "rubber", "tapioca"] as const;
export type Crop = (typeof CROPS)[number];

export function isCrop(v: string): v is Crop {
  return (CROPS as readonly string[]).includes(v);
}

/** Headline market per crop (first market of config/channel.yaml: the channel's lead market). */
export const REF_MARKET: Record<Crop, string> = {
  banana: "Kayamkulam",
  coconut: "Koduvayoor",
  pepper: "Kannur",
  rubber: "Kalpetta",
  tapioca: "Payyannur",
};

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
