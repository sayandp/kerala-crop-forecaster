import { ImageResponse } from "next/og";

export const ogSize = { width: 1200, height: 630 };
export const ogContentType = "image/png";

/** Shared Open Graph card (English text: default OG fonts have no Malayalam glyphs). */
export function ogImage(title: string, subtitle: string): ImageResponse {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "64px",
          background: "#fcfcfb",
          color: "#0b0b0b",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", fontSize: 30, color: "#52514e" }}>cropcast · Kerala mandi prices</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "flex", fontSize: 72, fontWeight: 700 }}>{title}</div>
          <div style={{ display: "flex", fontSize: 34, color: "#52514e" }}>{subtitle}</div>
        </div>
        <div style={{ display: "flex", height: 12, width: "100%", background: "#2a78d6", borderRadius: 6 }} />
      </div>
    ),
    ogSize,
  );
}
