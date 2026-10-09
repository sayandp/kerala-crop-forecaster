import React from "react";
import { AbsoluteFill, Composition, Img, Still, continueRender, delayRender, staticFile } from "remotion";
import { Horizontal, HSTART, H_TOTAL } from "./Horizontal";
import { C, FONT, FONT_EN, FPS } from "./theme";
import { Backdrop, Glass, Phone, Sprout, Title } from "./ui";
import { Vertical, VSTART, V_TOTAL } from "./Vertical";

// Noto Sans Malayalam + Noto Sans (OFL, variable weight), copied into capture/fonts by render.mjs
const fontsReady = delayRender("fonts");
Promise.all(
  [
    ["Noto Sans Malayalam", "fonts/NotoSansMalayalam.ttf"],
    ["Noto Sans", "fonts/NotoSans.ttf"],
  ].map(([family, file]) => {
    const face = new FontFace(family, `url(${staticFile(file)})`, { weight: "100 900" });
    return face.load().then((f) => document.fonts.add(f));
  }),
)
  .then(() => continueRender(fontsReady))
  .catch((e) => {
    console.error(e);
    continueRender(fontsReady);
  });

const ThumbV: React.FC = () => (
  <AbsoluteFill>
    <Backdrop />
    <AbsoluteFill style={{ alignItems: "center", paddingTop: 110, gap: 50 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
        <Sprout size={110} />
        <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 64, color: C.ink }}>കേരള വിപണി വില</div>
      </div>
      <div style={{ maxWidth: 960 }}>
        <Title ml="ഇന്നത്തെ വില, 7 ദിവസത്തെ പ്രതീക്ഷ" en="Kerala crop prices + 7-day range — free" size={74} />
      </div>
      <Phone src="web/m-home-full.png" pageHeight={6103} pan={[[0, 0]]} width={560} />
    </AbsoluteFill>
  </AbsoluteFill>
);

const ThumbH: React.FC = () => (
  <AbsoluteFill>
    <Backdrop />
    <AbsoluteFill style={{ flexDirection: "row", alignItems: "center", padding: "0 80px", gap: 60 }}>
      <div style={{ width: 760, display: "flex", flexDirection: "column", gap: 34 }}>
        <Sprout size={110} />
        <div style={{ fontFamily: FONT_EN, fontWeight: 850, fontSize: 84, color: C.ink, lineHeight: 1.05, letterSpacing: -1 }}>
          Kerala crop prices, honestly forecast
        </div>
        <div style={{ fontFamily: FONT_EN, fontSize: 36, color: C.inkSoft, lineHeight: 1.3 }}>
          Self-retraining MLOps · calibrated 80% range · Telegram bot · ₹0 infra
        </div>
        <div style={{ display: "flex", gap: 16 }}>
          {["17 crops", "Malayalam + English", "Live accuracy"].map((s) => (
            <div key={s} style={{ padding: "10px 22px", borderRadius: 30, background: C.accentSoft, color: C.accent, fontFamily: FONT_EN, fontSize: 26, fontWeight: 750, whiteSpace: "nowrap" }}>
              {s}
            </div>
          ))}
        </div>
      </div>
      <Glass style={{ padding: 14, borderRadius: 30, transform: "rotate(-1.5deg)" }}>
        <Img src={staticFile("web/d-home-light.png")} style={{ width: 960, borderRadius: 20, display: "block" }} />
      </Glass>
    </AbsoluteFill>
  </AbsoluteFill>
);

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Vertical" component={Vertical} durationInFrames={V_TOTAL} fps={FPS} width={1080} height={1920} defaultProps={{ sections: VSTART }} />
    <Composition id="Horizontal" component={Horizontal} durationInFrames={H_TOTAL} fps={FPS} width={1920} height={1080} defaultProps={{ sections: HSTART }} />
    <Still id="ThumbVertical" component={ThumbV} width={1080} height={1920} />
    <Still id="ThumbHorizontal" component={ThumbH} width={1920} height={1080} />
  </>
);
