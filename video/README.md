# Demo videos

Two demo videos of Kerala Crop Price Forecaster, generated end to end from real output. No screen
was recorded by hand and no bot reply was typed in.

| Video | Format | For |
|---|---|---|
| `out/kerala-crop-vertical.mp4` | 1080×1920, ~59 s, Malayalam only (captions Malayalam first, English below) | farmers (WhatsApp, Reels) |
| `out/kerala-crop-horizontal.mp4` | 1920×1080, ~94 s, English | LinkedIn, README |

Both are H.264, yuv420p (limited range), `+faststart`, silent.

## How the footage is made

1. **Website** (`scripts/capture-web.mjs`, Playwright with local Chrome) against production,
   https://kerala-crop-forecaster.vercel.app:
   - mobile 390×844 (Malayalam, light): full-page screenshots at DPR 3, with the fixed chrome hidden
     and captured separately. Remotion pans them with eased keyframes under the real chrome.
   - desktop 1440×900 (English): scripted screen recordings with slow eased scrolls and pauses
     (light), plus screenshots in light and dark.
   - `scripts/anchors.mjs` measures section positions (`#history`, `#high`, `#markets`, …) so the
     pans stop on them.
2. **Telegram bot** (`scripts/capture_bot.py`): runs the bot's own handlers and renderers
   (`cropcast.bot`) against the live Neon database. Prices are read through the read-only role, the
   bot's own rows use `cropcast_bot`, sending is stubbed and the chat id is fake. Every row it
   creates is deleted afterwards (the script checks that 0 rows are left). The fired-alert messages
   (Malayalam and English) are the bot's real `alert_fired_above` texts built from the real latest
   price (`--alerts-only` re-renders just these, read-only). The channel post is rendered by the
   `notify` step's own `gather` / `render_post` and is not sent.
3. **Remotion** (`src/`) animates all of this in a generic messenger-style UI (own design, no
   third-party logos) and in glass cards that match the dashboard. Chart numbers come from the
   captured data and `reports/band_calibration_2026-10-08`. Fonts: Noto Sans Malayalam and Noto
   Sans (OFL, `assets/fonts/`).

## Craft (video-shotcraft + remotion-best-practices)

Visual language comes from the dashboard itself (`web/app/globals.css` tokens: paddy-green accent,
glass cards, agri gradient; dark title cards use the dark-mode background). Moves and seams are
adapted from video-shotcraft shot cards, with the parameters of their reference demos
(`src/motion.tsx`):

| Where | Shot card | Use |
|---|---|---|
| Website opening (both) | `crane-rise-reveal` | hold on one real price, rise (out-quad) to the whole page |
| Best market (both) | `speed-ramp-freeze` · freeze-annotate | the real recording freezes; a hand-drawn ellipse (8f) circles "Best market today: Parassala ₹70" |
| Home → crop page | `shot-transitions` C focus-handoff | 16f blur/drift exchange, 2f stagger |
| Crop page → small onion | `shot-transitions` E whip-pan (brake) | 8f out, long ease-out tail in |
| Light → dark (B) | `shot-transitions` A flash-cut | white only on the hard cut |
| Chapters (bot, how it works) | `shot-transitions` D dark title card | typed title, 8f fades |

Every cut sits on a fixed 100 BPM grid (18 frames per beat), so a track can be laid under later
without re-cutting. Captions: 56 px (Malayalam) / 56 px (English, horizontal) per aesthetic rule
Q11; key frames and the wordmark hold ≥ 1 s (R1).

Deliberate deviations from the aesthetic rules (as the rules require, written down):
- **S1–S5 (sound): the videos are silent.** The skill's BGM and SFX library is under the Mixkit
  licence, not CC0; the brief allowed only CC0 music (credited) or none.
- **Final independent review by a separate agent was not run**; frames of every section were
  checked by hand at each round (`out/frames/`).
- The crane starts at 1.8–2.0× instead of 3.2× so the texture (DPR 2–3) stays sharp (Q2).

## Re-render

```bash
cd video
npm install
npm run capture:web && node scripts/anchors.mjs   # production footage -> capture/web
npm run capture:bot                               # real bot replies   -> capture/bot (needs ../.env)
npm run render                                    # -> out/*.mp4, out/*.png, out/frames/*.png
```

`npm run studio` opens the Remotion editor. `node scripts/stills.mjs Horizontal 300 900` renders
preview frames. `capture/` and `out/` are gitignored. This folder is never deployed (Vercel builds
only `web/`).
