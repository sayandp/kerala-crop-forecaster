// Camera moves and seams, adapted from video-shotcraft shot cards (parameters from their demo
// sources) and re-skinned with the dashboard tokens:
//   crane-rise-reveal (opening), speed-ramp-freeze · freeze-annotate (rhythm),
//   shot-transitions A flash-cut / C focus-handoff / D dark title card / E whip-pan brake.
// Timing sits on a fixed 100 BPM grid (18 frames per beat) so a track can be laid under later;
// the videos ship silent (the skill's audio library is Mixkit-licensed, not CC0).
import React, { useId } from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { C, FONT, clamp } from "./theme";

export const BEAT = 18;
export const b = (n: number) => Math.round(n * BEAT);

/** crane-rise-reveal: hold on one real detail, then rise (Easing.out(quad), one progress for
 * focal point + scale) until the whole frame is in view; true rest afterwards (R1). */
export const Crane: React.FC<{
  focal: { x: number; y: number }; // output px of the detail at scale 1
  center: { x: number; y: number }; // output px the detail is shown at (usually frame centre)
  zoom: number;
  hold?: number;
  move?: number;
  children: React.ReactNode;
}> = ({ focal, center, zoom, hold = 20, move = 70, children }) => {
  const f = useCurrentFrame();
  const p = Easing.out(Easing.quad)(Math.min(1, Math.max(0, (f - hold) / move)));
  const s = zoom + (1 - zoom) * p;
  // the point that sits at the frame centre slides from the detail to the frame centre
  const fx = focal.x + (center.x - focal.x) * p;
  const fy = focal.y + (center.y - focal.y) * p;
  return (
    <AbsoluteFill style={{ transformOrigin: "0 0", transform: `translate(${center.x - fx * s}px, ${center.y - fy * s}px) scale(${s})` }}>
      {children}
    </AbsoluteFill>
  );
};

/** freeze-annotate marker: rough hand-drawn ellipse (feTurbulence scale 7), 8f stroke, then an
 * arrow (6f); fades over 8f before the picture moves again. Frames are local to the freeze. */
export const Annotate: React.FC<{
  cx: number;
  cy: number;
  rx: number;
  ry: number;
  dur: number;
  width: number;
  height: number;
  arrow?: "left" | "right";
  stroke?: number;
}> = ({ cx, cy, rx, ry, dur, width, height, arrow = "right", stroke = 8 }) => {
  const f = useCurrentFrame();
  const id = `rough-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const draw = interpolate(f, [6, 14], [0, 1], clamp);
  const arrowDraw = interpolate(f, [14, 20], [0, 1], clamp);
  const fade = interpolate(f, [dur - 8, dur], [1, 0], clamp);
  const len = Math.PI * (3 * (rx + ry) - Math.sqrt((3 * rx + ry) * (rx + 3 * ry)));
  const sx = arrow === "right" ? 1 : -1;
  const ax = cx + sx * (rx + 120);
  const ay = cy - ry - 110;
  return (
    <svg width={width} height={height} style={{ position: "absolute", inset: 0, pointerEvents: "none", opacity: fade }}>
      <defs>
        <filter id={id}>
          <feTurbulence type="fractalNoise" baseFrequency="0.02" numOctaves="2" seed="7" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="7" />
        </filter>
      </defs>
      <ellipse
        cx={cx}
        cy={cy}
        rx={rx}
        ry={ry}
        fill="none"
        stroke={C.orange}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={len}
        strokeDashoffset={len * (1 - draw)}
        transform={`rotate(-3 ${cx} ${cy})`}
        filter={`url(#${id})`}
      />
      <path
        d={`M ${ax} ${ay} Q ${cx + sx * (rx + 20)} ${ay + 20} ${cx + sx * rx * 0.75} ${cy - ry - 8}`}
        fill="none"
        stroke={C.orange}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={420}
        strokeDashoffset={420 * (1 - arrowDraw)}
        filter={`url(#${id})`}
      />
    </svg>
  );
};

export type Seam = "cut" | "focus" | "whip" | "flash" | "fade";

/** Wraps one shot; animates its entry / exit for the given seams. Neighbouring shots overlap by
 * the seam's length (see OVERLAP). Focus-handoff: out 16f blur 0→8 + drift 60, in 16f starting
 * 2f later, 8→0 + drift −50. Whip (brake): out 8f, ~1.5 screens; in = fast 30% then a long
 * ease-out tail (≤ 48f). Flash: white peak on the cut, 5f each side. */
export const OVERLAP: Record<Seam, number> = { cut: 0, focus: 16, whip: 4, flash: 0, fade: 10 };

export const Shot: React.FC<{
  dur: number;
  width: number;
  enter?: Seam;
  exit?: Seam;
  children: React.ReactNode;
}> = ({ dur, width, enter = "cut", exit = "cut", children }) => {
  const f = useCurrentFrame();
  let opacity = 1;
  let blur = 0;
  let x = 0;
  let blurX = 0;
  if (enter === "focus") {
    const t = interpolate(f, [2, 18], [0, 1], { ...clamp, easing: Easing.bezier(0.3, 0, 0.2, 1) });
    opacity *= t;
    blur += (1 - t) * 8;
    x += (1 - t) * -50;
  } else if (enter === "whip") {
    const t = interpolate(f, [0, 44], [0, 1], { ...clamp, easing: Easing.out(Easing.poly(5)) });
    x += width * 0.9 * (1 - t);
    blurX += interpolate(f, [0, 10], [36, 0], clamp);
  } else if (enter === "fade") {
    opacity *= interpolate(f, [0, 10], [0, 1], clamp);
  }
  if (exit === "focus") {
    const t = interpolate(f, [dur - 16, dur], [0, 1], { ...clamp, easing: Easing.bezier(0.45, 0, 0.3, 1) });
    opacity *= 1 - t;
    blur += t * 8;
    x -= t * 60;
  } else if (exit === "whip") {
    const t = interpolate(f, [dur - 8, dur], [0, 1], { ...clamp, easing: Easing.in(Easing.cubic) });
    x -= width * 1.5 * t;
    blurX += t * 40;
  } else if (exit === "fade") {
    opacity *= interpolate(f, [dur - 10, dur], [1, 0], clamp);
  }
  const id = `whip-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <AbsoluteFill
      style={{
        opacity,
        transform: x ? `translateX(${x}px)` : undefined,
        filter: [blur > 0.01 ? `blur(${blur}px)` : "", blurX > 0.5 ? `url(#${id})` : ""].join(" ").trim() || undefined,
      }}
    >
      {blurX > 0.5 ? (
        <svg width={0} height={0} style={{ position: "absolute" }}>
          <filter id={id}>
            <feGaussianBlur stdDeviation={`${blurX} 0`} />
          </filter>
        </svg>
      ) : null}
      {children}
    </AbsoluteFill>
  );
};

/** shot-transitions A: a white flash that only covers a hard cut (never decorative, Q4). */
export const FlashCut: React.FC<{ at: number }> = ({ at }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [at - 5, at, at + 5], [0, 0.9, 0], clamp);
  return o > 0 ? <AbsoluteFill style={{ background: "#fff", opacity: o, pointerEvents: "none" }} /> : null;
};

/** shot-transitions D: dark chapter card in the dashboard's dark-mode colours; the title is
 * typed in, holds, and the card fades over 8f at both ends. */
export const ChapterCard: React.FC<{ dur: number; title: string; sub?: string; size: number }> = ({ dur, title, sub, size }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 8, dur - 8, dur], [0, 1, 1, 0], clamp);
  const chars = [...title];
  const n = Math.ceil(interpolate(f, [6, 6 + chars.length * 1.4], [0, chars.length], clamp));
  return (
    <AbsoluteFill style={{ background: "#0d1511", opacity: o, alignItems: "center", justifyContent: "center", flexDirection: "column", gap: size * 0.3 }}>
      <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: size, color: C.bgA, letterSpacing: -0.5 }}>
        {chars.slice(0, n).join("")}
        <span style={{ opacity: n < chars.length ? 1 : 0, color: C.paddy }}>|</span>
      </div>
      {sub ? (
        <div style={{ fontFamily: FONT, fontSize: size * 0.42, color: C.paddy, opacity: interpolate(f, [18, 28], [0, 1], clamp) }}>{sub}</div>
      ) : null}
    </AbsoluteFill>
  );
};
