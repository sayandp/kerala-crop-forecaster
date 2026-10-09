// A generic, unbranded messenger UI that replays the REAL bot replies captured by
// scripts/capture_bot.py (capture/bot/conversation.json). Nothing here invents bot text.
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, clamp } from "./theme";
import { Sprout } from "./ui";

export type Entry = { from: "user" | "bot"; text: string; tap?: string | null; buttons?: string[][] | null };

type Item = {
  who: "user" | "bot";
  text: string;
  buttons?: string[][] | null;
  at: number; // frame the bubble appears
  typeFrom?: number; // user: frame typing starts in the input bar
  tapAt?: number; // bot: frame one of its buttons is tapped
  tapped?: string;
};

/** Turn the captured conversation into a timed script (frames relative to the chat start). */
export function schedule(entries: Entry[], start = 10, pace = 1): { items: Item[]; end: number } {
  const items: Item[] = [];
  let t = start;
  for (const e of entries) {
    if (e.from === "user" && e.tap) {
      // a button tap sends no message: highlight the button on the previous bot bubble
      const prev = [...items].reverse().find((i) => i.who === "bot" && i.buttons);
      if (prev) {
        prev.tapAt = t;
        prev.tapped = e.tap;
      }
      t += 14;
      continue;
    }
    if (e.from === "user") {
      const typing = Math.round(Math.min(34, 8 + e.text.length * 1.3) * pace);
      items.push({ who: "user", text: e.text, typeFrom: t, at: t + typing });
      t += typing + 6;
    } else {
      t += 16; // "typing…" dots
      items.push({ who: "bot", text: e.text, buttons: e.buttons, at: t });
      const read = Math.min(110, Math.max(34, e.text.length * 0.45)) + (e.buttons ? 26 : 0);
      t += Math.round(read * pace);
    }
  }
  return { items, end: t };
}

/** Commands and links in the accent colour, as a messenger would show them. */
const Rich: React.FC<{ text: string; light?: boolean }> = ({ text, light }) => {
  const parts = text.split(/(https?:\/\/\S+|(?<=^|\s)\/[a-z]+)/g);
  return (
    <>
      {parts.map((p, i) =>
        /^(https?:\/\/|\/[a-z])/.test(p) && (i === 0 || /(^|\s)$/.test(parts[i - 1]) || p.startsWith("http")) && !light ? (
          <span key={i} style={{ color: "#1f6fbf" }}>
            {p}
          </span>
        ) : (
          <React.Fragment key={i}>{p}</React.Fragment>
        ),
      )}
    </>
  );
};

const Bubble: React.FC<{ item: Item; fs: number }> = ({ item, fs }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f - item.at, fps, config: { damping: 20, stiffness: 120 } });
  const user = item.who === "user";
  return (
    // grid 0fr -> 1fr animates the row height so older bubbles glide up
    <div style={{ display: "grid", gridTemplateRows: `${Math.min(1, p)}fr` }}>
      <div style={{ minHeight: 0, overflow: "hidden" }}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: user ? "flex-end" : "flex-start",
            padding: `${fs * 0.3}px 0`,
            opacity: p,
            transform: `translateY(${(1 - p) * 20}px) scale(${0.96 + 0.04 * p})`,
            transformOrigin: user ? "right bottom" : "left bottom",
          }}
        >
          <div
            style={{
              maxWidth: "84%",
              background: user ? C.accent : "#fff",
              color: user ? "#fff" : C.ink,
              borderRadius: fs * 0.9,
              borderBottomRightRadius: user ? fs * 0.25 : fs * 0.9,
              borderBottomLeftRadius: user ? fs * 0.9 : fs * 0.25,
              padding: `${fs * 0.45}px ${fs * 0.7}px`,
              fontFamily: FONT,
              fontSize: fs,
              lineHeight: 1.45,
              whiteSpace: "pre-wrap",
              boxShadow: "0 3px 12px rgba(30,60,40,0.12)",
            }}
          >
            <Rich text={item.text} light={user} />
          </div>
          {item.buttons ? <Buttons item={item} fs={fs} /> : null}
        </div>
      </div>
    </div>
  );
};

const Buttons: React.FC<{ item: Item; fs: number }> = ({ item, fs }) => {
  const f = useCurrentFrame();
  return (
    <div style={{ width: "84%", display: "flex", flexDirection: "column", gap: fs * 0.25, marginTop: fs * 0.25 }}>
      {item.buttons!.map((row, r) => (
        <div key={r} style={{ display: "flex", gap: fs * 0.25 }}>
          {row.map((b) => {
            const hit = item.tapped === b && item.tapAt !== undefined;
            const d = hit ? f - item.tapAt! : -1;
            const press = hit ? interpolate(d, [-8, 0, 8], [1, 0.93, 1], clamp) : 1;
            const on = hit && d >= 0;
            const ring = hit ? interpolate(d, [0, 18], [0, 1], clamp) : 0;
            return (
              <div
                key={b}
                style={{
                  position: "relative",
                  flex: 1,
                  textAlign: "center",
                  padding: `${fs * 0.42}px ${fs * 0.3}px`,
                  borderRadius: fs * 0.5,
                  background: on ? C.accent : "rgba(255,255,255,0.78)",
                  color: on ? "#fff" : C.accent,
                  fontFamily: FONT,
                  fontWeight: 650,
                  fontSize: fs * 0.92,
                  border: `1.5px solid ${on ? C.accent : "rgba(29,106,67,0.25)"}`,
                  transform: `scale(${press})`,
                  boxShadow: "0 2px 8px rgba(30,60,40,0.08)",
                }}
              >
                {b}
                {hit && d >= 0 && d < 18 ? (
                  <div
                    style={{
                      position: "absolute",
                      left: "50%",
                      top: "50%",
                      width: fs * 3 * ring,
                      height: fs * 3 * ring,
                      marginLeft: (-fs * 3 * ring) / 2,
                      marginTop: (-fs * 3 * ring) / 2,
                      borderRadius: "50%",
                      border: `3px solid rgba(29,106,67,${1 - ring})`,
                    }}
                  />
                ) : null}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
};

const Dots: React.FC<{ fs: number }> = ({ fs }) => {
  const f = useCurrentFrame();
  return (
    <div style={{ display: "flex", padding: `${fs * 0.3}px 0` }}>
      <div style={{ background: "#fff", borderRadius: fs, padding: `${fs * 0.55}px ${fs * 0.7}px`, display: "flex", gap: fs * 0.25 }}>
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            style={{
              width: fs * 0.32,
              height: fs * 0.32,
              borderRadius: "50%",
              background: C.inkSoft,
              opacity: 0.35 + 0.65 * Math.max(0, Math.sin((f - i * 4) / 4)),
            }}
          />
        ))}
      </div>
    </div>
  );
};

export const Chat: React.FC<{
  items: Item[];
  width: number;
  height: number;
  fs: number;
  title: string;
  style?: React.CSSProperties;
}> = ({ items, width, height, fs, title, style }) => {
  const f = useCurrentFrame();
  const shown = items.filter((i) => f >= i.at);
  const typingBot = items.some((i) => i.who === "bot" && f >= i.at - 16 && f < i.at);
  const typingUser = items.find((i) => i.who === "user" && i.typeFrom !== undefined && f >= i.typeFrom && f < i.at);
  const typed = typingUser
    ? typingUser.text.slice(0, Math.ceil(((f - typingUser.typeFrom!) / (typingUser.at - typingUser.typeFrom! - 4)) * typingUser.text.length))
    : "";
  const head = fs * 3.1;
  const input = fs * 2.8;
  return (
    <div
      style={{
        width,
        height,
        borderRadius: fs * 1.6,
        overflow: "hidden",
        background: "linear-gradient(180deg, #e3eddc 0%, #efe8d6 100%)",
        border: `1.5px solid ${C.glassEdge}`,
        boxShadow: "0 40px 90px rgba(20,45,30,0.30)",
        display: "flex",
        flexDirection: "column",
        ...style,
      }}
    >
      <div
        style={{
          height: head,
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: fs * 0.6,
          padding: `0 ${fs * 0.8}px`,
          background: "rgba(255,255,255,0.86)",
          borderBottom: "1px solid rgba(22,33,27,0.08)",
        }}
      >
        <Sprout size={fs * 1.9} />
        <div style={{ fontFamily: FONT, lineHeight: 1.25 }}>
          <div style={{ fontWeight: 700, fontSize: fs * 0.95, color: C.ink }}>{title}</div>
          <div style={{ fontSize: fs * 0.72, color: C.inkSoft }}>@keralacropprices_bot · bot</div>
        </div>
      </div>
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-end",
          padding: `0 ${fs * 0.7}px`,
        }}
      >
        {shown.map((it, i) => (
          <Bubble key={i} item={it} fs={fs} />
        ))}
        {typingBot ? <Dots fs={fs} /> : null}
        <div style={{ height: fs * 0.5, flex: "none" }} />
      </div>
      <div
        style={{
          height: input,
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: fs * 0.5,
          padding: `0 ${fs * 0.7}px`,
          background: "rgba(255,255,255,0.86)",
          borderTop: "1px solid rgba(22,33,27,0.08)",
        }}
      >
        <div
          style={{
            flex: 1,
            height: fs * 1.8,
            borderRadius: fs,
            background: "rgba(22,33,27,0.05)",
            display: "flex",
            alignItems: "center",
            padding: `0 ${fs * 0.7}px`,
            fontFamily: FONT,
            fontSize: fs * 0.92,
            color: typed ? C.ink : "rgba(22,33,27,0.4)",
            whiteSpace: "nowrap",
            overflow: "hidden",
          }}
        >
          {typed || "Message"}
          {typed ? <span style={{ opacity: Math.floor(f / 8) % 2 ? 0 : 1, color: C.accent }}>|</span> : null}
        </div>
        <div style={{ width: fs * 1.8, height: fs * 1.8, borderRadius: "50%", background: C.accent, display: "grid", placeItems: "center" }}>
          <svg width={fs * 0.9} height={fs * 0.9} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.6} strokeLinecap="round">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </div>
      </div>
    </div>
  );
};

/** A push-style notification card with the real fired-alert text. */
export const Notification: React.FC<{ text: string; fs: number; width: number; delay?: number }> = ({ text, fs, width, delay = 0 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f - delay, fps, config: { damping: 16, stiffness: 120 } });
  return (
    <div
      style={{
        width,
        transform: `translateY(${(1 - p) * -260}px)`,
        opacity: p,
        background: "rgba(255,255,255,0.93)",
        borderRadius: fs * 1.1,
        padding: fs * 0.8,
        boxShadow: "0 24px 60px rgba(20,45,30,0.28)",
        border: `1.5px solid ${C.glassEdge}`,
        display: "flex",
        gap: fs * 0.7,
      }}
    >
      <Sprout size={fs * 2.1} />
      <div style={{ flex: 1, fontFamily: FONT }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: fs * 0.74, color: C.inkSoft, marginBottom: fs * 0.2 }}>
          <span style={{ fontWeight: 700 }}>@keralacropprices_bot</span>
          <span>now</span>
        </div>
        <div style={{ fontSize: fs, lineHeight: 1.45, color: C.ink, whiteSpace: "pre-wrap" }}>{text}</div>
      </div>
    </div>
  );
};

/** The real daily channel post, scrolled slowly inside a channel-style frame. */
export const ChannelPost: React.FC<{ text: string; width: number; height: number; fs: number; scroll: number }> = ({
  text,
  width,
  height,
  fs,
  scroll,
}) => {
  const lines = text.split("\n");
  return (
    <div
      style={{
        width,
        height,
        borderRadius: fs * 1.6,
        overflow: "hidden",
        background: "linear-gradient(180deg, #e3eddc 0%, #efe8d6 100%)",
        border: `1.5px solid ${C.glassEdge}`,
        boxShadow: "0 40px 90px rgba(20,45,30,0.30)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          height: fs * 3.1,
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: fs * 0.6,
          padding: `0 ${fs * 0.8}px`,
          background: "rgba(255,255,255,0.86)",
          zIndex: 1,
        }}
      >
        <Sprout size={fs * 1.9} bg={C.accentSoft} fg={C.accent} />
        <div style={{ fontFamily: FONT, lineHeight: 1.25 }}>
          <div style={{ fontWeight: 700, fontSize: fs * 0.95, color: C.ink }}>കേരള വിപണി വില</div>
          <div style={{ fontSize: fs * 0.72, color: C.inkSoft }}>t.me/keralavipanivila · channel</div>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden", padding: `${fs * 0.8}px ${fs * 0.7}px` }}>
        <div
          style={{
            transform: `translateY(${-scroll}px)`,
            background: "#fff",
            borderRadius: fs * 0.9,
            padding: `${fs * 0.6}px ${fs * 0.8}px`,
            fontFamily: FONT,
            fontSize: fs,
            lineHeight: 1.45,
            color: C.ink,
            boxShadow: "0 3px 12px rgba(30,60,40,0.12)",
          }}
        >
          {lines.map((l, i) => (
            <div
              key={i}
              style={{
                minHeight: l ? undefined : fs * 0.6,
                fontWeight: i < 2 || (l && !l.startsWith(" ") && !l.startsWith("•") && i < lines.length - 2) ? 700 : 400,
                color: l.startsWith("  ") ? C.inkSoft : C.ink,
                fontSize: l.startsWith("  ") ? fs * 0.9 : fs,
                whiteSpace: "pre-wrap",
              }}
            >
              {l}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
