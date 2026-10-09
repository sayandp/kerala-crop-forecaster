# Demo videos

Two demo videos of Kerala Crop Price Forecaster, generated end to end from real output. No screen
was recorded by hand and no bot reply was typed in.

| Video | Format | For |
|---|---|---|
| `out/kerala-crop-vertical.mp4` | 1080×1920, ~63 s, Malayalam captions first, English below | farmers (WhatsApp, Reels) |
| `out/kerala-crop-horizontal.mp4` | 1920×1080, ~92 s, English | LinkedIn, README |

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
   creates is deleted afterwards (the script checks that 0 rows are left). The fired-alert message
   is the real `alert_fired_above` text built from the real latest price. The channel post is
   rendered by the `notify` step's own `gather` / `render_post` and is not sent.
3. **Remotion** (`src/`) animates all of this in a generic messenger-style UI (own design, no
   third-party logos) and in glass cards that match the dashboard. Chart numbers come from the
   captured data and `reports/band_calibration_2026-10-08`. Fonts: Noto Sans Malayalam and Noto
   Sans (OFL, `assets/fonts/`). No music.

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
