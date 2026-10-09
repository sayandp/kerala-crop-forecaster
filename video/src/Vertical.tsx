// Video A — vertical 1080x1920 for farmers (WhatsApp / Reels). Malayalam captions first.
import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import conv from "../capture/bot/conversation.json";
import anchors from "../capture/web/anchors.json";
import meta from "../capture/web/meta.json";
import { Chat, ChannelPost, Entry, Notification, schedule } from "./chat";
import { Cta, Hook, Problem } from "./scenes";
import { C, FONT, FONT_EN, keys } from "./theme";
import { Backdrop, Cap, Captions, Glass, Phone, Pop, Scene } from "./ui";

const chat = schedule(conv.conversation as Entry[], 12, 0.5);
const at = (t: string) => chat.items.find((i) => i.text === t)!.typeFrom!;
const ALERT_AT = at("/alert നേന്ത്രൻ");
const LANG_AT = at("/lang en");
const H = (k: keyof typeof meta.shots) => meta.shots[k].height;
const A = anchors as Record<string, Record<string, number>>;
const top = (page: string, id: string) => A[page][id] - 84; // leave room for the site's top bar

// scene lengths (frames @30 fps)
export const V = {
  hook: 96,
  problem: 165,
  home: 200,
  banana: 290,
  onion: 95,
  chat: chat.end + 20,
  alert: 105,
  channel: 165,
  range: 150,
  cta: 170,
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
  { from: S.home, to: S.home + 110, ml: "17 വിളകൾ — ഇന്നത്തെ വിലയും ഒരാഴ്ചയിലെ മാറ്റവും", en: "17 crops — today's price and the change over a week" },
  { from: S.home + 110, to: S.banana, ml: "നാണ്യവിളകൾ, വാഴപ്പഴങ്ങൾ, പച്ചക്കറികൾ", en: "Cash crops, bananas, vegetables" },
  { from: S.banana, to: S.banana + 140, ml: "വില ചരിത്രവും 7 ദിവസത്തെ പ്രതീക്ഷിത പരിധിയും", en: "Price history and the 7-day expected range" },
  { from: S.banana + 140, to: S.banana + 205, ml: "ഈ വില കൂടുതലാണോ? കഴിഞ്ഞ വർഷങ്ങളുമായി താരതമ്യം", en: "Is this price high? Compared with past years" },
  { from: S.banana + 205, to: S.onion, ml: "എല്ലാ വിപണികളും — ഏറ്റവും നല്ല വില എവിടെ", en: "Every market — where the best price is" },
  { from: S.onion, to: S.chat, ml: "ചെറിയ ഉള്ളി, തക്കാളി, പച്ചമുളക്… എല്ലാം ഒരിടത്ത്", en: "Small onion, tomato, green chilli… all in one place" },
  { from: S.chat, to: S.chat + ALERT_AT, ml: "ടെലിഗ്രാം ബോട്ടിൽ മലയാളത്തിൽ ചോദിക്കാം", en: "Ask the Telegram bot in Malayalam" },
  { from: S.chat + ALERT_AT, to: S.chat + LANG_AT, ml: "വിപണി ബട്ടൺ അമർത്തി വില അറിയിപ്പ് സജ്ജമാക്കാം", en: "Tap a market to set a price alert" },
  { from: S.chat + LANG_AT, to: S.alert, ml: "ഇംഗ്ലീഷിലും ഉപയോഗിക്കാം", en: "Works in English too" },
  { from: S.alert, to: S.channel, ml: "വില നിങ്ങൾ പറഞ്ഞ തുക കടന്നാൽ സന്ദേശം", en: "A message when the price crosses your level" },
  { from: S.channel, to: S.range, ml: "എല്ലാ ദിവസവും രാവിലെ ചാനലിൽ വില", en: "Every morning, prices in the channel" },
  { from: S.range, to: S.cta, ml: "ഇത് ഒരു പരിധി മാത്രം, ഉറപ്പല്ല", en: "A range, not a guarantee" },
  { from: S.cta, to: V_TOTAL, ml: "ചാനലിലും ബോട്ടിലും ചേരൂ", en: "Join the channel and the bot" },
];

const RealChip: React.FC = () => (
  <div style={{ position: "absolute", top: 46, width: "100%", display: "flex", justifyContent: "center" }}>
    <Pop>
      <div style={{ padding: "12px 30px", borderRadius: 40, background: C.accent, color: "#fff", fontFamily: FONT_EN, fontWeight: 700, fontSize: 30 }}>
        Real replies from @keralacropprices_bot
      </div>
    </Pop>
  </div>
);

const PhoneScene: React.FC<{ src: string; page: keyof typeof meta.shots; pan: [number, number][] }> = ({ src, page, pan }) => (
  <AbsoluteFill style={{ alignItems: "center", paddingTop: 80 }}>
    <Phone src={src} pageHeight={H(page)} pan={pan} width={650} />
  </AbsoluteFill>
);

const ChannelScene: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: 130 }}>
      <ChannelPost text={conv.channel_post} width={960} height={1430} fs={29} scroll={keys(f, [[0, 0], [25, 0], [150, 2300]])} />
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
      <PhoneScene
        src="web/m-home-full.png"
        page="m-home-full"
        pan={[[0, 0], [40, 0], [95, top("m-home", "#group-banana")], [130, top("m-home", "#group-banana")], [180, top("m-home", "#group-veg")], [200, top("m-home", "#group-veg")]]}
      />
    </Sequence>
    <Sequence from={S.banana} durationInFrames={V.banana}>
      <PhoneScene
        src="web/m-banana-full.png"
        page="m-banana-full"
        pan={[[0, 0], [30, 0], [70, top("m-banana", "#history")], [130, top("m-banana", "#history")], [160, top("m-banana", "#high")], [200, top("m-banana", "#high")], [235, top("m-banana", "#markets")], [290, top("m-banana", "#markets") + 120]]}
      />
    </Sequence>
    <Sequence from={S.onion} durationInFrames={V.onion}>
      <PhoneScene src="web/m-small-onion-full.png" page="m-small-onion-full" pan={[[0, 0], [20, 0], [60, top("m-small-onion", "#high")], [95, top("m-small-onion", "#high")]]} />
    </Sequence>
    <Sequence from={S.chat} durationInFrames={V.chat}>
      <RealChip />
      <AbsoluteFill style={{ alignItems: "center", paddingTop: 130 }}>
        <Chat items={chat.items} width={960} height={1430} fs={30} title="കേരള വിപണി വില ബോട്ട്" />
      </AbsoluteFill>
    </Sequence>
    <Sequence from={S.alert} durationInFrames={V.alert}>
      <Scene dur={V.alert}>
        <RealChip />
        <AbsoluteFill style={{ alignItems: "center", paddingTop: 420 }}>
          <Notification text={conv.alert_example.text} fs={34} width={940} delay={8} />
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
            <Glass style={{ padding: "22px 36px", width: 900, textAlign: "center" }}>
              <div style={{ fontFamily: FONT, fontSize: 38, fontWeight: 800, color: C.ink, lineHeight: 1.4 }}>
                10-ൽ 8 തവണ യഥാർത്ഥ വില ഈ പരിധിക്കുള്ളിൽ
              </div>
              <div style={{ fontFamily: FONT_EN, fontSize: 27, color: C.inkSoft, marginTop: 6 }}>
                The real price landed inside the range 81% of the time (target 80%)
              </div>
            </Glass>
          </Pop>
          <Phone src="web/m-accuracy-full.png" pageHeight={H("m-accuracy-full")} pan={[[0, 0], [30, 0], [140, 700]]} width={500} />
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
