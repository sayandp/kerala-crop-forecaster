import { ImageResponse } from "next/og";
import { ML, OG_ASCENT, OG_DESCENT, OG_UPEM } from "@/lib/og-glyphs";

export const ogSize = { width: 1200, height: 630 };
export const ogContentType = "image/png";

const BG =
  "radial-gradient(60% 60% at 10% 0%, #a9c8e6 0%, transparent 70%), radial-gradient(60% 60% at 100% 30%, #f0c98a 0%, transparent 70%), radial-gradient(70% 60% at 30% 100%, #9cc49a 0%, transparent 70%), linear-gradient(180deg, #e8f0e1, #f3ead9)";

/** A pre-shaped Malayalam phrase (lib/og-glyphs.ts) as inline SVG, `size` px font size. */
function MlText({ k, size, color = "#10140f" }: { k: string; size: number; color?: string }) {
  const g = ML[k];
  if (!g) return null;
  const h = OG_ASCENT + OG_DESCENT;
  return (
    <svg
      width={(g.w * size) / OG_UPEM}
      height={(h * size) / OG_UPEM}
      viewBox={`0 ${-OG_ASCENT} ${g.w} ${h}`}
      style={{ display: "flex" }}
    >
      <path d={g.d} fill={color} />
    </svg>
  );
}

/** Shared Open Graph card for evidence pages (English text; Malayalam brand pre-shaped). */
export function ogImage(title: string, subtitle: string): ImageResponse {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", padding: 48, background: BG, fontFamily: "sans-serif" }}>
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            padding: 56,
            borderRadius: 44,
            background: "rgba(255,255,255,0.72)",
            border: "2px solid rgba(255,255,255,0.9)",
            boxShadow: "0 30px 60px -30px rgba(30,45,20,0.45)",
            color: "#10140f",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <MlText k="brand" size={40} color="#1d6a43" />
            <span style={{ fontSize: 30, color: "#39432f" }}>· cropcast</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", fontSize: 70, fontWeight: 700 }}>{title}</div>
            <div style={{ display: "flex", fontSize: 34, color: "#39432f" }}>{subtitle}</div>
          </div>
          <div style={{ display: "flex", height: 10, width: 220, background: "#1d6a43", borderRadius: 6 }} />
        </div>
      </div>
    ),
    ogSize,
  );
}

export interface CropOg {
  crop: string; // key: banana | coconut | ...
  cropEn: string;
  market: string; // canonical (English) market name
  price: number | null; // Rs./kg
  lo: number;
  hi: number;
  date: string; // "8 Oct"
}

/** Per-crop share card styled like the glass UI; Malayalam crop/market/labels pre-shaped. */
export function cropOgImage(c: CropOg): ImageResponse {
  const ink = "#10140f";
  const ink2 = "#39432f";
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", padding: 44, background: BG, fontFamily: "sans-serif" }}>
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            padding: "44px 56px",
            borderRadius: 44,
            background: "rgba(255,255,255,0.74)",
            border: "2px solid rgba(255,255,255,0.92)",
            boxShadow: "0 30px 60px -30px rgba(30,45,20,0.45)",
            color: ink,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <MlText k="brand" size={34} color="#1d6a43" />
            <span style={{ fontSize: 26, color: ink2 }}>{c.date} · Agmarknet</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
              <MlText k={`crop:${c.crop}`} size={78} />
              <span style={{ fontSize: 40, color: ink2 }}>{c.cropEn}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <MlText k={`market:${c.market}`} size={38} color={ink2} />
              <span style={{ fontSize: 30, color: ink2 }}>· {c.market.replace(/ VFPCK$/, "")}</span>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 12 }}>
              <span style={{ fontSize: 120, fontWeight: 700, lineHeight: 1 }}>₹{c.price ?? "–"}</span>
              <div style={{ display: "flex", paddingBottom: 14 }}>
                <MlText k="perKg" size={34} color={ink2} />
              </div>
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-end",
                gap: 6,
                padding: "18px 24px",
                borderRadius: 28,
                background: "rgba(255,255,255,0.9)",
              }}
            >
              <MlText k="in7" size={30} color={ink2} />
              <span style={{ fontSize: 52, fontWeight: 700 }}>
                ₹{c.lo}–{c.hi}
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <MlText k="notGuarantee" size={24} color={ink2} />
                <span style={{ fontSize: 22, color: ink2 }}>/ not a guarantee</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    ),
    ogSize,
  );
}
