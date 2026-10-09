// Video A — vertical 1080x1920 for farmers (WhatsApp / Reels). Malayalam only, captions in
// Malayalam first with an English line below. Cuts sit on the 18-frame beat grid (motion.tsx).
import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import conv from "../capture/bot/conversation.json";
import anchors from "../capture/web/anchors.json";
import meta from "../capture/web/meta.json";
import { Chat, ChannelPost, Entry, Notification, schedule } from "./chat";
import { Annotate, ChapterCard, Crane, OVERLAP, Shot, b } from "./motion";
import { Cta, Hook, Problem } from "./scenes";
import { C, FONT, FONT_EN, keys } from "./theme";
import { Backdrop, Cap, Captions, Glass, Phone, Pop, Scene } from "./ui";

// Malayalam part of the real conversation only: /start, /price, /alert, market tap -> thresholds
const ML = (conv.conversation as Entry[]).slice(0, 8);
const chat = schedule(ML, 12, 0.6);
const at = (t: string) => chat.items.find((i) => i.text === t)!.typeFrom!;
const ALERT_AT = at("/alert നേന്ത്രൻ");

const H = (k: keyof typeof meta.shots) => meta.shots[k].height;
const A = anchors as Record<string, Record<string, number>>;
const top = (page: string, id: string) => A[page][id] - 84; // leave room for the site's top bar
const ceilBeat = (n: number) => Math.ceil(n / 18) * 18;

// Phone geometry (output px): 650 px screen = 390 CSS px.
const PW = 650;
const PS = PW / 390;
const SX = (1080 - (PW + 32)) / 2 + 16; // screen left
const SY = 80 + 16; // screen top
const BANANA_Y = top("m-home", "#group-banana");
// "Best market today: Parassala ₹70" on the Nendran card (CSS px on m-home-full.png)
const BEST = { x: 195, y: 2497, w: 323, h: 38 };

// scene lengths (frames @30 fps, whole beats)
export const V = {
  hook: b(6),
  problem: b(8),
  home: b(12),
  banana: b(14),
  onion: b(4),
  chapter: b(3),
  chat: ceilBeat(chat.end + 24),
  alert: b(6),
  channel: b(8),
  range: b(7),
  cta: b(9),
};
const order = Object.keys(V) as (keyof typeof V)[];
export const VSTART = Object.fromEntries(
  order.map((k, i) => [k, order.slice(0, i).reduce((s, j) => s + V[j], 0)]),
) as Record<keyof typeof V, number>;
export const V_TOTAL = order.reduce((s, k) => s + V[k], 0);
const S = VSTART;

const CAPS: Cap[] = [
  { from: 0, to: S.problem, ml: "ഇന്നത്തെ വിപണി വില, 7 ദിവസത്തെ പ്രതീക്ഷ", en: "Kerala crop prices + 7-day expected range — free" },
  { from: S.problem, to: S.home, ml: "ഏത് വിപണിയിൽ കൂടുതൽ വില കിട്ടും എന്നറിയാതെയാണ് പലരും വിൽക്കുന്നത്", en: "Farmers often sell without knowing which market pays more" },
  { from: S.home, to: S.home + 120, ml: "17 വിളകൾ — ഇന്നത്തെ വിലയും ഒരാഴ്ചയിലെ മാറ്റവും", en: "17 crops — today's price and the change over a week" },
  { from: S.home + 120, to: S.banana, ml: "ഇന്ന് ഏറ്റവും നല്ല വില കിട്ടുന്ന വിപണി", en: "The market paying the most today" },
  { from: S.banana, to: S.banana + 140, ml: "വില ചരിത്രവും 7 ദിവസത്തെ പ്രതീക്ഷിത പരിധിയും", en: "Price history and the 7-day expected range" },
  { from: S.banana + 140, to: S.onion, ml: "ഈ വില കൂടുതലാണോ? കഴിഞ്ഞ വർഷങ്ങളുമായി താരതമ്യം", en: "Is this price high? Compared with past years" },
  { from: S.onion, to: S.chapter, ml: "ചെറിയ ഉള്ളി, തക്കാളി, പച്ചമുളക്… എല്ലാം ഒരിടത്ത്", en: "Small onion, tomato, green chilli… all in one place" },
  { from: S.chat, to: S.chat + ALERT_AT, ml: "ടെലിഗ്രാം ബോട്ടിൽ മലയാളത്തിൽ ചോദിക്കാം", en: "Ask the Telegram bot in Malayalam" },
  { from: S.chat + ALERT_AT, to: S.alert, ml: "വിപണി ബട്ടൺ അമർത്തി വില അറിയിപ്പ് സജ്ജമാക്കാം", en: "Tap a market to set a price alert" },
  { from: S.alert, to: S.channel, ml: "വില നിങ്ങൾ പറഞ്ഞ തുക കടന്നാൽ സന്ദേശം", en: "A message when the price crosses your level" },
  { from: S.channel, to: S.range, ml: "എല്ലാ ദിവസവും രാവിലെ ചാനലിൽ വില", en: "Every morning, prices in the channel" },
  { from: S.range, to: S.cta, ml: "ഇത് ഒരു പരിധി മാത്രം, ഉറപ്പല്ല", en: "A range, not a guarantee" },
  { from: S.cta, to: V_TOTAL, ml: "ചാനലിലും ബോട്ടിലും ചേരൂ", en: "Join the channel and the bot" },
];

const RealChip: React.FC = () => (
  <div style={{ position: "absolute", top: 40, width: "100%", display: "flex", justifyContent: "center" }}>
    <Pop>
      <div style={{ padding: "12px 30px", borderRadius: 40, background: C.accent, color: "#fff", fontFamily: FONT_EN, fontWeight: 700, fontSize: 32 }}>
        Real replies from @keralacropprices_bot
      </div>
    </Pop>
  </div>
);

const PhoneAt: React.FC<{ src: string; page: keyof typeof meta.shots; pan: [number, number][] }> = ({ src, page, pan }) => (
  <AbsoluteFill style={{ alignItems: "center", paddingTop: 80 }}>
    <Phone src={src} pageHeight={H(page)} pan={pan} width={PW} />
  </AbsoluteFill>
);

/** Home: crane-rise from the first real price, pan to the bananas, then freeze on the
 * Nendran card and circle its best market (freeze-annotate). */
const HomeShot: React.FC = () => {
  const FREEZE = 140;
  const HOLD = b(3);
  return (
    <>
      <Crane focal={{ x: SX + 66 * PS, y: SY + 367 * PS }} center={{ x: 540, y: 800 }} zoom={1.8} hold={20} move={70}>
        <PhoneAt src="web/m-home-full.png" page="m-home-full" pan={[[0, 0], [96, 0], [136, BANANA_Y], [V.home, BANANA_Y]]} />
      </Crane>
      <Sequence from={FREEZE} durationInFrames={HOLD}>
        <Annotate
          cx={SX + BEST.x * PS}
          cy={SY + (BEST.y - BANANA_Y) * PS}
          rx={(BEST.w / 2) * PS + 34}
          ry={BEST.h * PS * 0.5 + 28}
          dur={HOLD}
          width={1080}
          height={1920}
        />
      </Sequence>
    </>
  );
};

const ChannelScene: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: 130 }}>
      <ChannelPost text={conv.channel_post} width={960} height={1430} fs={29} scroll={keys(f, [[0, 0], [30, 0], [V.channel - 20, 2300]])} />
    </AbsoluteFill>
  );
};

export const Vertical: React.FC<{ sections: Record<string, number> }> = () => (
  <AbsoluteFill style={{ fontFamily: FONT }}>
    <Backdrop />
    <Sequence durationInFrames={V.hook}>
      <Scene dur={V.hook}>
        <Hook v />
      </Scene>
    </Sequence>
    <Sequence from={S.problem} durationInFrames={V.problem}>
      <Scene dur={V.problem}>
        <Problem v />
      </Scene>
    </Sequence>
    <Sequence from={S.home} durationInFrames={V.home}>
      <Shot dur={V.home} width={1080} enter="fade" exit="focus">
        <HomeShot />
      </Shot>
    </Sequence>
    <Sequence from={S.banana - OVERLAP.focus} durationInFrames={V.banana + OVERLAP.focus}>
      <Shot dur={V.banana + OVERLAP.focus} width={1080} enter="focus" exit="whip">
        <PhoneAt
          src="web/m-banana-full.png"
          page="m-banana-full"
          pan={[[0, 0], [40, 0], [80, top("m-banana", "#history")], [135, top("m-banana", "#history")], [165, top("m-banana", "#high")], [V.banana, top("m-banana", "#high")]]}
        />
      </Shot>
    </Sequence>
    <Sequence from={S.onion - OVERLAP.whip} durationInFrames={V.onion + OVERLAP.whip}>
      <Shot dur={V.onion + OVERLAP.whip} width={1080} enter="whip" exit="fade">
        <PhoneAt src="web/m-small-onion-full.png" page="m-small-onion-full" pan={[[0, 0], [V.onion, 0]]} />
      </Shot>
    </Sequence>
    <Sequence from={S.chapter} durationInFrames={V.chapter}>
      <ChapterCard dur={V.chapter} title="ടെലിഗ്രാം ബോട്ട്" sub="@keralacropprices_bot" size={84} />
    </Sequence>
    <Sequence from={S.chat} durationInFrames={V.chat}>
      <RealChip />
      <AbsoluteFill style={{ alignItems: "center", paddingTop: 130 }}>
        <Chat items={chat.items} width={960} height={1430} fs={31} title="കേരള വിപണി വില ബോട്ട്" />
      </AbsoluteFill>
    </Sequence>
    <Sequence from={S.alert} durationInFrames={V.alert}>
      <Scene dur={V.alert}>
        <RealChip />
        <AbsoluteFill style={{ alignItems: "center", paddingTop: 460 }}>
          <Notification text={conv.alert_example_ml.text} fs={36} width={960} delay={8} />
        </AbsoluteFill>
      </Scene>
    </Sequence>
    <Sequence from={S.channel} durationInFrames={V.channel}>
      <Scene dur={V.channel}>
        <ChannelScene />
      </Scene>
    </Sequence>
    <Sequence from={S.range} durationInFrames={V.range}>
      <Scene dur={V.range}>
        <AbsoluteFill style={{ alignItems: "center", paddingTop: 70, gap: 30 }}>
          <Pop>
            <Glass style={{ padding: "22px 36px", width: 940, textAlign: "center" }}>
              <div style={{ fontFamily: FONT, fontSize: 42, fontWeight: 800, color: C.ink, lineHeight: 1.4 }}>
                10-ൽ 8 തവണ യഥാർത്ഥ വില ഈ പരിധിക്കുള്ളിൽ
              </div>
              <div style={{ fontFamily: FONT_EN, fontSize: 32, color: C.inkSoft, marginTop: 6 }}>
                Real price inside the range 81% of the time (target 80%)
              </div>
            </Glass>
          </Pop>
          <Phone src="web/m-accuracy-full.png" pageHeight={H("m-accuracy-full")} pan={[[0, 0], [30, 0], [V.range - 10, 700]]} width={500} />
        </AbsoluteFill>
      </Scene>
    </Sequence>
    <Sequence from={S.cta} durationInFrames={V.cta}>
      <Scene dur={V.cta + 12}>
        <Cta v />
      </Scene>
    </Sequence>
    <Captions caps={CAPS} layout="vertical" />
  </AbsoluteFill>
);
