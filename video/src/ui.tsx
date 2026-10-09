import React from "react";
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, FONT, FONT_EN, clamp, keys, shadow } from "./theme";

/** Soft agri gradient with slowly drifting colour blobs (paddy, turmeric, monsoon sky). */
export const Backdrop: React.FC = () => {
  const f = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const m = Math.max(width, height);
  const blob = (color: string, x: number, y: number, r: number, phase: number) => (
    <div
      style={{
        position: "absolute",
        left: x * width + Math.sin(f / 90 + phase) * m * 0.03 - r * m * 0.5,
        top: y * height + Math.cos(f / 110 + phase) * m * 0.03 - r * m * 0.5,
        width: r * m,
        height: r * m,
        borderRadius: "50%",
        background: color,
        filter: `blur(${m * 0.09}px)`,
        opacity: 0.55,
      }}
    />
  );
  return (
    <AbsoluteFill style={{ background: `linear-gradient(160deg, ${C.bgA} 0%, ${C.bgB} 100%)`, overflow: "hidden" }}>
      {blob(C.sky, 0.08, 0.1, 0.55, 0)}
      {blob(C.turmeric, 0.92, 0.35, 0.45, 2)}
      {blob(C.paddy, 0.3, 0.95, 0.6, 4)}
    </AbsoluteFill>
  );
};

export const Glass: React.FC<{ style?: React.CSSProperties; children?: React.ReactNode; opaque?: boolean }> = ({
  style,
  children,
  opaque,
}) => (
  <div
    style={{
      background: opaque ? C.data : C.glass,
      border: `1.5px solid ${C.glassEdge}`,
      borderRadius: 36,
      boxShadow: shadow,
      ...style,
    }}
  >
    {children}
  </div>
);

/** Fade + gentle lift in, fade out at the end of a sequence. */
export const Scene: React.FC<{ dur: number; children: React.ReactNode }> = ({ dur, children }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 10, dur - 10, dur], [0, 1, 1, 0], clamp);
  const y = interpolate(f, [0, 14], [18, 0], clamp);
  return <AbsoluteFill style={{ opacity: o, transform: `translateY(${y}px)` }}>{children}</AbsoluteFill>;
};

export const useSpring = (delay = 0, damping = 18) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: f - delay, fps, config: { damping, mass: 0.9, stiffness: 110 } });
};

/** Pop-in wrapper (spring scale + fade), starting `delay` frames into the sequence. */
export const Pop: React.FC<{ delay?: number; children: React.ReactNode; style?: React.CSSProperties; from?: number }> = ({
  delay = 0,
  children,
  style,
  from = 0.92,
}) => {
  const s = useSpring(delay);
  return (
    <div style={{ opacity: s, transform: `translateY(${(1 - s) * 30}px) scale(${from + (1 - from) * s})`, ...style }}>
      {children}
    </div>
  );
};

export const Sprout: React.FC<{ size: number; bg?: string; fg?: string }> = ({ size, bg = C.accent, fg = "#fff" }) => (
  <div
    style={{
      width: size,
      height: size,
      borderRadius: size * 0.26,
      background: bg,
      display: "grid",
      placeItems: "center",
      boxShadow: "0 8px 22px rgba(29,106,67,0.35)",
      flex: "none",
    }}
  >
    <svg width={size * 0.56} height={size * 0.56} viewBox="0 0 24 24" fill="none" stroke={fg} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 21v-9" />
      <path d="M12 12c0-4 2.5-7 7-7 0 4.5-3 7-7 7z" />
      <path d="M12 14c0-3.5-2.2-6-6-6 0 3.8 2.5 6 6 6z" />
    </svg>
  </div>
);

export type Cap = { from: number; to: number; ml?: string; en: string };

/** Always-on captions: Malayalam line first (vertical), English below. */
export const Captions: React.FC<{ caps: Cap[]; layout: "vertical" | "horizontal" }> = ({ caps, layout }) => {
  const f = useCurrentFrame();
  const cur = caps.find((c) => f >= c.from && f < c.to);
  if (!cur) return null;
  const t = f - cur.from;
  const o = interpolate(t, [0, 8], [0, 1], clamp) * interpolate(f, [cur.to - 8, cur.to], [1, 0], clamp);
  const y = interpolate(t, [0, 12], [16, 0], clamp);
  const v = layout === "vertical";
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", pointerEvents: "none" }}>
      <div
        style={{
          marginBottom: v ? 60 : 26,
          maxWidth: v ? 1000 : 1760,
          padding: v ? "24px 40px" : "14px 38px",
          borderRadius: v ? 40 : 30,
          background: "rgba(16,32,22,0.80)",
          color: "#fff",
          textAlign: "center",
          opacity: o,
          transform: `translateY(${y}px)`,
          boxShadow: "0 12px 40px rgba(0,0,0,0.25)",
        }}
      >
        {cur.ml && v ? (
          <div style={{ fontFamily: FONT, fontSize: 56, fontWeight: 700, lineHeight: 1.4 }}>{cur.ml}</div>
        ) : null}
        <div
          style={{
            fontFamily: FONT_EN,
            fontSize: v ? (cur.ml ? 36 : 52) : 56,
            fontWeight: v && cur.ml ? 500 : 650,
            opacity: v && cur.ml ? 0.82 : 1,
            marginTop: v && cur.ml ? 8 : 0,
            lineHeight: 1.35,
          }}
        >
          {cur.en}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/**
 * A phone showing a full-page mobile screenshot (390 CSS px wide, DPR 3), panned along eased
 * keyframes (CSS px from the top), with the site's own fixed chrome laid over it.
 */
export const Phone: React.FC<{
  src: string;
  pageHeight: number;
  pan: [number, number][];
  width: number;
  chrome?: boolean;
  style?: React.CSSProperties;
}> = ({ src, pageHeight, pan, width, chrome = true, style }) => {
  const f = useCurrentFrame();
  const s = width / 390;
  const vh = 844;
  const y = Math.max(0, Math.min(pageHeight - vh, keys(f, pan)));
  const bezel = 16;
  return (
    <div
      style={{
        width: width + bezel * 2,
        height: vh * s + bezel * 2,
        borderRadius: 64,
        background: "#1b231e",
        padding: bezel,
        boxShadow: "0 40px 90px rgba(20,45,30,0.35), 0 0 0 2px rgba(255,255,255,0.4) inset",
        ...style,
      }}
    >
      <div style={{ position: "relative", width, height: vh * s, borderRadius: 50, overflow: "hidden", background: C.bgA }}>
        <Img src={staticFile(src)} style={{ position: "absolute", left: 0, top: 0, width, transform: `translateY(${-y * s}px)` }} />
        {chrome ? (
          <>
            <Img src={staticFile("web/m-chrome-top.png")} style={{ position: "absolute", left: 0, top: 8 * s, width }} />
            <Img src={staticFile("web/m-chrome-tabs.png")} style={{ position: "absolute", left: 0, bottom: 10 * s, width }} />
          </>
        ) : null}
      </div>
    </div>
  );
};

/** A plain, unbranded browser window showing a desktop recording or screenshot. */
export const Browser: React.FC<{
  url: string;
  width: number;
  video?: string;
  trimBefore?: number;
  image?: string;
  style?: React.CSSProperties;
}> = ({ url, width, video, trimBefore = 0, image, style }) => {
  const h = (width * 900) / 1440;
  return (
    <div style={{ borderRadius: 26, overflow: "hidden", boxShadow: "0 40px 90px rgba(20,45,30,0.30)", border: `1.5px solid ${C.glassEdge}`, ...style }}>
      <div style={{ height: 58, background: "rgba(250,252,248,0.96)", display: "flex", alignItems: "center", padding: "0 22px", gap: 18 }}>
        <div style={{ display: "flex", gap: 9 }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ width: 13, height: 13, borderRadius: 7, background: "rgba(22,33,27,0.18)" }} />
          ))}
        </div>
        <div
          style={{
            flex: 1,
            maxWidth: 760,
            margin: "0 auto",
            height: 36,
            borderRadius: 18,
            background: "rgba(22,33,27,0.06)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: FONT_EN,
            fontSize: 20,
            color: C.inkSoft,
          }}
        >
          {url}
        </div>
        <div style={{ width: 66 }} />
      </div>
      <div style={{ width, height: h, background: "#fff", position: "relative" }}>
        {video ? (
          <OffthreadVideo src={staticFile(video)} trimBefore={trimBefore} muted style={{ width, height: h }} />
        ) : image ? (
          <Img src={staticFile(image)} style={{ width, height: h }} />
        ) : null}
      </div>
    </div>
  );
};

export const Title: React.FC<{ ml?: string; en: string; size: number; align?: "center" | "left"; showMl?: boolean }> = ({
  ml,
  en,
  size,
  align = "center",
  showMl = true,
}) => (
  <div style={{ textAlign: align, color: C.ink }}>
    {ml && showMl ? (
      <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: size, lineHeight: 1.35 }}>{ml}</div>
    ) : null}
    <div
      style={{
        fontFamily: FONT_EN,
        fontWeight: ml && showMl ? 550 : 800,
        fontSize: ml && showMl ? size * 0.56 : size,
        color: ml && showMl ? C.inkSoft : C.ink,
        marginTop: ml && showMl ? size * 0.25 : 0,
        lineHeight: 1.25,
        letterSpacing: ml && showMl ? 0 : -0.5,
      }}
    >
      {en}
    </div>
  </div>
);
