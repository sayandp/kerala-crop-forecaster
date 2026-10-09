// Scenes shared by both videos. Every number here is real: market prices from the captured bot /
// channel output (8 Oct 2026), coverage from reports/band_calibration_2026-10-08, model facts from
// CLAUDE.md / promotion_log.
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, FONT, FONT_EN, clamp } from "./theme";
import { Glass, Pop, Sprout, Title, useSpring } from "./ui";

type L = { v: boolean }; // vertical (Malayalam-first) vs horizontal (English)

// ------------------------------------------------------------------ hook
const HOOK_CHIPS = [
  { ml: "തേങ്ങ", en: "Coconut", market: "Koduvayoor", price: 54, lo: 51, hi: 59 },
  { ml: "നേന്ത്രക്കായ", en: "Nendran banana", market: "Kayamkulam", price: 51, lo: 45, hi: 56 },
  { ml: "കുരുമുളക്", en: "Black pepper", market: "Kannur", price: 680, lo: 673, hi: 683 },
];

export const Hook: React.FC<L> = ({ v }) => (
  <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap: v ? 60 : 44 }}>
    <Pop>
      <Sprout size={v ? 150 : 120} />
    </Pop>
    <Pop delay={4} style={{ maxWidth: v ? 960 : 1500 }}>
      <Title
        ml="ഇന്നത്തെ വിപണി വില, 7 ദിവസത്തെ പ്രതീക്ഷ"
        en="Kerala crop prices + 7-day expected range — free"
        size={v ? 76 : 74}
        showMl={v}
      />
    </Pop>
    <div style={{ display: "flex", flexDirection: v ? "column" : "row", gap: v ? 22 : 30, marginTop: v ? 10 : 20 }}>
      {HOOK_CHIPS.map((c, i) => (
        <Pop key={c.en} delay={12 + i * 6}>
          <Glass style={{ padding: v ? "22px 34px" : "22px 34px", display: "flex", alignItems: "center", gap: 26, minWidth: v ? 760 : 0 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontFamily: FONT, fontWeight: 700, fontSize: v ? 38 : 32, color: C.ink }}>{v ? c.ml : c.en}</div>
              <div style={{ fontFamily: FONT_EN, fontSize: v ? 26 : 22, color: C.inkSoft }}>{c.market}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontFamily: FONT_EN, fontWeight: 800, fontSize: v ? 56 : 48, color: C.ink }}>₹{c.price}</div>
              <div style={{ fontFamily: v ? FONT : FONT_EN, fontSize: v ? 24 : 21, color: C.accent, fontWeight: 600 }}>
                {v ? `7 ദിവസം: ₹${c.lo}–${c.hi}` : `7 days: ₹${c.lo}–${c.hi}`}
              </div>
            </div>
          </Glass>
        </Pop>
      ))}
    </div>
  </AbsoluteFill>
);

// ------------------------------------------------------------------ problem
// Nendran banana, modal price on 8 Oct 2026 at every market that reported that day (from /price).
const BANANA = [
  { ml: "പാറശ്ശാല", en: "Parassala", p: 70 },
  { ml: "ഇളമാട്", en: "Elamad", p: 68 },
  { ml: "തിരുവാണിയൂർ", en: "Thiruvaniyoor", p: 68 },
  { ml: "കുന്നുകര", en: "Kunnukara", p: 66 },
  { ml: "ചെങ്കൽ", en: "Chenkal", p: 64 },
  { ml: "മൂക്കന്നൂർ", en: "Mookkannur", p: 60 },
  { ml: "കായംകുളം", en: "Kayamkulam", p: 51 },
];

export const Problem: React.FC<L> = ({ v }) => {
  const f = useCurrentFrame();
  const W = v ? 900 : 1300;
  const barW = W - (v ? 360 : 360);
  const max = 75;
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: v ? "flex-start" : "center", paddingTop: v ? 250 : 0 }}>
      <Pop>
        <Title
          ml="ഒരേ ദിവസം, ഒരേ വിള — വിപണി മാറിയാൽ വില മാറും"
          en="Same day, same crop — the price depends on the market"
          size={v ? 58 : 56}
          showMl={v}
        />
      </Pop>
      <Pop delay={8} style={{ marginTop: v ? 50 : 40 }}>
        <Glass opaque style={{ width: W, padding: v ? "34px 40px" : "30px 44px" }}>
          <div style={{ fontFamily: v ? FONT : FONT_EN, fontSize: v ? 30 : 26, fontWeight: 700, color: C.ink }}>
            {v ? "നേന്ത്രക്കായ · ₹/കിലോ · 8 ഒക്ടോ 2026" : "Nendran banana · ₹/kg · 8 Oct 2026"}
          </div>
          <div style={{ fontFamily: FONT_EN, fontSize: v ? 22 : 20, color: C.inkSoft, marginBottom: 22 }}>
            {v ? "Agmarknet മൊത്തവില" : "Agmarknet wholesale modal price, every market that reported that day"}
          </div>
          {BANANA.map((b, i) => {
            const g = interpolate(f, [16 + i * 4, 46 + i * 4], [0, 1], { ...clamp, easing: (t) => 1 - Math.pow(1 - t, 3) });
            const ext = i === 0 || i === BANANA.length - 1;
            return (
              <div key={b.en} style={{ display: "flex", alignItems: "center", height: v ? 66 : 58 }}>
                <div style={{ width: v ? 250 : 240, fontFamily: v ? FONT : FONT_EN, fontSize: v ? 30 : 26, color: C.ink, fontWeight: ext ? 700 : 400 }}>
                  {v ? b.ml : b.en}
                </div>
                <div style={{ width: barW, position: "relative", height: v ? 40 : 34 }}>
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: barW * (b.p / max) * g,
                      background: C.blue,
                      opacity: ext ? 1 : 0.55,
                      borderRadius: 8,
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      left: barW * (b.p / max) * g + 12,
                      top: "50%",
                      transform: "translateY(-50%)",
                      fontFamily: FONT_EN,
                      fontWeight: 750,
                      fontSize: v ? 30 : 26,
                      color: C.ink,
                      opacity: g,
                    }}
                  >
                    ₹{b.p}
                  </div>
                </div>
              </div>
            );
          })}
          <div
            style={{
              marginTop: 20,
              fontFamily: v ? FONT : FONT_EN,
              fontSize: v ? 30 : 28,
              fontWeight: 700,
              color: C.accent,
              opacity: interpolate(f, [70, 85], [0, 1], clamp),
            }}
          >
            {v ? "വ്യത്യാസം: കിലോയ്ക്ക് ₹19 (37%)" : "Gap: ₹19 per kg (37%) on the same day"}
          </div>
        </Glass>
      </Pop>
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ pipeline (horizontal only)
type Node = { id: string; x: number; y: number; w: number; title: string; sub: string; at: number; tone?: "accent" | "soft" };
const NODES: Node[] = [
  { id: "agm", x: 60, y: 300, w: 330, title: "Agmarknet", sub: "daily mandi prices, 2018 →", at: 0 },
  { id: "met", x: 60, y: 520, w: 330, title: "Open-Meteo", sub: "district rain + temperature", at: 6 },
  { id: "gha", x: 500, y: 400, w: 380, title: "GitHub Actions", sub: "every morning 05:00 IST\ningest · validate · clean · predict", at: 24, tone: "accent" },
  { id: "mlf", x: 500, y: 120, w: 380, title: "MLflow on DagsHub", sub: "weekly retrain · registry\nchampion / challenger gate", at: 54 },
  { id: "neon", x: 990, y: 400, w: 330, title: "Neon Postgres", sub: "prices · forecasts · live accuracy", at: 84 },
  { id: "api", x: 1430, y: 230, w: 400, title: "Render · FastAPI", sub: "read-only API", at: 110 },
  { id: "web", x: 1430, y: 420, w: 400, title: "Vercel · dashboard", sub: "Malayalam + English, PWA", at: 118 },
  { id: "tg", x: 1430, y: 610, w: 400, title: "Telegram", sub: "channel post + bot alerts", at: 126 },
];
const H_NODE = 150;
const EDGES: [string, string, number][] = [
  ["agm", "gha", 16],
  ["met", "gha", 20],
  ["gha", "mlf", 44],
  ["mlf", "gha", 66],
  ["gha", "neon", 74],
  ["neon", "api", 100],
  ["neon", "web", 106],
  ["neon", "tg", 112],
];

export const Pipeline: React.FC<{ title?: boolean }> = ({ title = true }) => {
  const f = useCurrentFrame();
  const by = Object.fromEntries(NODES.map((n) => [n.id, n]));
  const path = (a: Node, b: Node, back: boolean) => {
    if (a.id === "gha" && b.id === "mlf") return `M ${a.x + a.w * 0.35} ${a.y} L ${b.x + b.w * 0.35} ${b.y + H_NODE}`;
    if (back) return `M ${a.x + a.w * 0.65} ${a.y + H_NODE} L ${b.x + b.w * 0.65} ${b.y}`;
    const x1 = a.x + a.w;
    const y1 = a.y + H_NODE / 2;
    const x2 = b.x;
    const y2 = b.y + H_NODE / 2;
    const mx = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
  };
  return (
    <AbsoluteFill>
      {title ? (
        <div style={{ position: "absolute", top: 40, width: "100%", textAlign: "center" }}>
          <Pop>
            <Title en="How it works" size={60} />
          </Pop>
        </div>
      ) : null}
      <svg width={1920} height={1080} style={{ position: "absolute", top: 60, left: 0 }}>
        <defs>
          <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill={C.accent} />
          </marker>
        </defs>
        {EDGES.map(([a, b, at], i) => {
          const d = path(by[a], by[b], a === "mlf");
          const p = interpolate(f, [at, at + 18], [0, 1], clamp);
          const flow = (f * 3) % 40;
          return (
            <g key={i} opacity={p > 0 ? 1 : 0}>
              <path d={d} fill="none" stroke={C.accent} strokeOpacity={0.25} strokeWidth={5} pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - p} />
              {p >= 1 ? (
                <path d={d} fill="none" stroke={C.accent} strokeWidth={4} strokeDasharray="10 30" strokeDashoffset={-flow} markerEnd="url(#arr)" />
              ) : null}
            </g>
          );
        })}
      </svg>
      <div style={{ position: "absolute", top: 60, left: 0, width: 1920, height: 1080 }}>
        {NODES.map((n) => (
          <div key={n.id} style={{ position: "absolute", left: n.x, top: n.y, width: n.w }}>
            <Pop delay={n.at}>
              <Glass
                opaque={n.tone !== "accent"}
                style={{
                  height: H_NODE,
                  padding: "20px 26px",
                  borderRadius: 28,
                  background: n.tone === "accent" ? C.accent : undefined,
                  color: n.tone === "accent" ? "#fff" : C.ink,
                }}
              >
                <div style={{ fontFamily: FONT_EN, fontWeight: 800, fontSize: 31 }}>{n.title}</div>
                <div style={{ fontFamily: FONT_EN, fontSize: 21, opacity: 0.8, whiteSpace: "pre-wrap", marginTop: 6, lineHeight: 1.35 }}>{n.sub}</div>
              </Glass>
            </Pop>
          </div>
        ))}
      </div>
      <div style={{ position: "absolute", bottom: 150, width: "100%", display: "flex", justifyContent: "center", gap: 26 }}>
        {["17 crops · 35 market series", "Runs itself every morning", "₹0 infrastructure (free tiers)"].map((s, i) => (
          <Pop key={s} delay={150 + i * 8}>
            <div style={{ padding: "14px 30px", borderRadius: 40, background: C.accentSoft, color: C.accent, fontFamily: FONT_EN, fontSize: 30, fontWeight: 750 }}>
              {s}
            </div>
          </Pop>
        ))}
      </div>
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ honest finding + coverage chart
// p10–p90 coverage per crop, raw -> calibrated (reports/band_calibration_2026-10-08/coverage_by_crop.csv)
const COVERAGE: [string, number, number][] = [
  ["Arecanut", 74.8, 82.4],
  ["Nendran banana", 80.1, 79.2],
  ["Bitter gourd", 82.2, 80.8],
  ["Coconut", 75.5, 81.8],
  ["Coffee", 74.0, 80.2],
  ["Cucumber", 77.6, 78.1],
  ["Drumstick", 76.8, 79.2],
  ["Ginger", 74.0, 78.0],
  ["Green chilli", 81.0, 81.6],
  ["Onion", 78.9, 81.6],
  ["Palayankodan", 77.4, 81.0],
  ["Black pepper", 89.4, 88.6],
  ["Poovan", 73.7, 81.6],
  ["Rubber", 82.1, 80.4],
  ["Small onion", 79.2, 81.2],
  ["Tapioca", 83.2, 84.2],
  ["Tomato", 81.3, 79.3],
];

export const Coverage: React.FC<{ width: number; delay?: number }> = ({ width, delay = 0 }) => {
  const f = useCurrentFrame() - delay;
  const rows: [string, number, number][] = [["All crops", 79.7, 81.3], ...[...COVERAGE].sort((a, b) => b[2] - a[2])];
  const labW = 210;
  const plotW = width - labW - 90;
  const lo = 70;
  const hi = 92;
  const x = (p: number) => labW + ((p - lo) / (hi - lo)) * plotW;
  const rh = 36;
  const top = 92;
  const H = top + rows.length * rh + 50;
  return (
    <svg width={width} height={H} style={{ fontFamily: FONT_EN }}>
      {/* target zone 70–90 and nominal 80 */}
      <rect x={x(70)} y={top - 10} width={x(90) - x(70)} height={rows.length * rh + 10} fill={C.aqua} opacity={0.1} />
      <line x1={x(80)} x2={x(80)} y1={top - 14} y2={top + rows.length * rh} stroke={C.ink} strokeDasharray="6 6" strokeWidth={2} opacity={0.55} />
      <text x={x(80)} y={top - 22} textAnchor="middle" fontSize={20} fill={C.ink} fontWeight={700}>
        target 80%
      </text>
      {[70, 75, 80, 85, 90].map((t) => (
        <text key={t} x={x(t)} y={top + rows.length * rh + 30} textAnchor="middle" fontSize={19} fill={C.inkSoft}>
          {t}%
        </text>
      ))}
      {/* legend */}
      <circle cx={labW} cy={18} r={9} fill="#fff" stroke={C.orange} strokeWidth={3.5} />
      <text x={labW + 18} y={25} fontSize={21} fill={C.ink}>
        model band (raw)
      </text>
      <circle cx={labW + 230} cy={18} r={9} fill={C.blue} />
      <text x={labW + 248} y={25} fontSize={21} fill={C.ink}>
        after calibration (shown on the site)
      </text>
      {rows.map(([name, raw, cal], i) => {
        const y = top + i * rh + rh / 2;
        const a = interpolate(f, [8 + i * 2, 26 + i * 2], [0, 1], clamp);
        const pos = raw + (cal - raw) * interpolate(f, [30 + i * 2, 60 + i * 2], [0, 1], clamp);
        const pooled = i === 0;
        return (
          <g key={name} opacity={a}>
            {pooled ? <rect x={0} y={y - rh / 2 + 2} width={width} height={rh - 4} rx={8} fill={C.accentSoft} opacity={0.7} /> : null}
            <text x={labW - 16} y={y + 7} textAnchor="end" fontSize={21} fill={C.ink} fontWeight={pooled ? 800 : 450}>
              {name}
            </text>
            <line x1={x(raw)} x2={x(pos)} y1={y} y2={y} stroke={C.blue} strokeWidth={3} opacity={0.5} />
            <circle cx={x(raw)} cy={y} r={8} fill="#fff" stroke={C.orange} strokeWidth={3} />
            <circle cx={x(pos)} cy={y} r={9} fill={C.blue} />
            {pooled ? (
              <text x={x(Math.max(raw, cal)) + 16} y={y + 7} fontSize={21} fontWeight={800} fill={C.ink}>
                {raw.toFixed(1)}% → {cal.toFixed(1)}%
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
};

export const Finding: React.FC = () => (
  <AbsoluteFill style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 50, padding: "0 70px 110px" }}>
    <div style={{ width: 760, display: "flex", flexDirection: "column", gap: 26 }}>
      <Pop>
        <div style={{ fontFamily: FONT_EN, fontSize: 30, fontWeight: 750, color: C.accent, letterSpacing: 1 }}>THE HONEST FINDING</div>
      </Pop>
      <Pop delay={6}>
        <div style={{ fontFamily: FONT_EN, fontSize: 54, fontWeight: 800, color: C.ink, lineHeight: 1.15 }}>
          Short-term prices are near-random.
        </div>
      </Pop>
      <Pop delay={20}>
        <Glass style={{ padding: "26px 32px" }}>
          <div style={{ fontFamily: FONT_EN, fontSize: 31, color: C.ink, lineHeight: 1.35 }}>
            So we show a <b>calibrated 80% range</b>, not fake precision. The point forecast is “last price” unless a model
            proves it is better.
          </div>
        </Glass>
      </Pop>
      <Pop delay={44}>
        <Glass style={{ padding: "26px 32px" }}>
          <div style={{ fontFamily: FONT_EN, fontSize: 31, color: C.ink, lineHeight: 1.35 }}>
            <b>LightGBM is promoted only where it beat the baseline</b>: 14-day horizon, 3.7% lower error than naive over 2
            years of walk-forward tests (Diebold–Mariano p &lt; 0.001). 1- and 7-day stay naive.
          </div>
        </Glass>
      </Pop>
    </div>
    <Pop delay={30}>
      <Glass opaque style={{ padding: "28px 30px 20px" }}>
        <div style={{ fontFamily: FONT_EN, fontSize: 27, fontWeight: 800, color: C.ink, marginBottom: 4 }}>
          How often the real price landed inside the 80% range
        </div>
        <div style={{ fontFamily: FONT_EN, fontSize: 20, color: C.inkSoft, marginBottom: 12 }}>
          34,650 out-of-sample forecasts, 26 walk-forward folds · shaded = 70–90% acceptance zone
        </div>
        <Coverage width={880} delay={34} />
      </Glass>
    </Pop>
  </AbsoluteFill>
);

// ------------------------------------------------------------------ CTA
const LINKS = [
  { ml: "ദിവസേന വില — ചാനൽ", en: "Daily prices — channel", url: "t.me/keralavipanivila" },
  { ml: "വില അറിയിപ്പ് — ബോട്ട്", en: "Price alerts — bot", url: "t.me/keralacropprices_bot" },
  { ml: "വെബ്സൈറ്റ്", en: "Website", url: "kerala-crop-forecaster.vercel.app" },
];

export const Cta: React.FC<L> = ({ v }) => {
  const s = useSpring(0);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap: v ? 40 : 34, paddingBottom: v ? 160 : 60 }}>
      <div style={{ transform: `scale(${0.9 + 0.1 * s})`, opacity: s }}>
        <Sprout size={v ? 130 : 100} />
      </div>
      <Pop delay={4}>
        <Title ml="സൗജന്യം · ഇന്നു തന്നെ തുടങ്ങാം" en="Free · start today" size={v ? 64 : 64} showMl={v} />
      </Pop>
      <div style={{ display: "flex", flexDirection: v ? "column" : "row", gap: v ? 24 : 28 }}>
        {LINKS.map((l, i) => (
          <Pop key={l.url} delay={12 + i * 7}>
            <Glass style={{ padding: v ? "26px 40px" : "26px 34px", width: v ? 880 : undefined }}>
              <div style={{ fontFamily: v ? FONT : FONT_EN, fontSize: v ? 32 : 26, color: C.inkSoft, fontWeight: 600 }}>{v ? l.ml : l.en}</div>
              <div style={{ fontFamily: FONT_EN, fontSize: v ? 42 : 34, color: C.accent, fontWeight: 800, marginTop: 6, whiteSpace: "nowrap" }}>{l.url}</div>
            </Glass>
          </Pop>
        ))}
      </div>
      <Pop delay={36}>
        <div style={{ fontFamily: v ? FONT : FONT_EN, fontSize: v ? 26 : 22, color: C.inkSoft, textAlign: "center" }}>
          {v ? "ഉറവിടം: Agmarknet · ഉറപ്പല്ല / not a guarantee" : "Source: Agmarknet · a range, not a guarantee · open source on GitHub"}
        </div>
      </Pop>
    </AbsoluteFill>
  );
};
