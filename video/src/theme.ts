// Visual tokens, taken from the dashboard (web/app/globals.css) so the video matches the site.
import { Easing, interpolate } from "remotion";

export const FPS = 30;

export const C = {
  accent: "#1d6a43", // dashboard accent (paddy green)
  accentSoft: "#d6e9da",
  ink: "#16211b",
  inkSoft: "#4a5a50",
  bgA: "#e8f0e1",
  bgB: "#f3ead9",
  paddy: "#9cc98a",
  turmeric: "#f1c75b",
  sky: "#9cc3df",
  glass: "rgba(255,255,255,0.62)",
  glassEdge: "rgba(255,255,255,0.85)",
  data: "rgba(255,255,255,0.94)",
  // dataviz slots (validated light palette)
  blue: "#2a78d6",
  orange: "#eb6834",
  aqua: "#1baf7a",
  grid: "rgba(22,33,27,0.12)",
  up: "#1f7a3d",
  down: "#b3261e",
};

export const FONT = `"Noto Sans Malayalam", "Noto Sans", system-ui, sans-serif`;
export const FONT_EN = `"Noto Sans", "Noto Sans Malayalam", system-ui, sans-serif`;

export const shadow = "0 1px 0 rgba(255,255,255,0.9) inset, 0 18px 50px rgba(30,60,40,0.18), 0 2px 8px rgba(30,60,40,0.10)";

const ease = Easing.inOut(Easing.cubic);

/** Piecewise eased keyframes: [[frame, value], ...]; equal neighbouring values = a hold. */
export function keys(f: number, k: [number, number][]): number {
  if (f <= k[0][0]) return k[0][1];
  for (let i = 0; i < k.length - 1; i++) {
    const [f0, v0] = k[i];
    const [f1, v1] = k[i + 1];
    if (f <= f1) return interpolate(f, [f0, f1], [v0, v1], { easing: ease });
  }
  return k[k.length - 1][1];
}

export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const sec = (s: number) => Math.round(s * FPS);
