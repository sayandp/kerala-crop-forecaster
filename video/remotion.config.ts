// Remotion config: captured footage + fonts are served from ./capture (gitignored; fonts are
// copied there from assets/ by scripts/render.mjs). Renders with the local Chrome when present.
import { Config } from "@remotion/cli/config";
import fs from "node:fs";

Config.setPublicDir("./capture");
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(92);
Config.setCodec("h264");
Config.setCrf(22);
Config.setPixelFormat("yuv420p");
Config.setConcurrency(4);
const chrome = process.env.REMOTION_CHROME ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
if (fs.existsSync(chrome)) Config.setBrowserExecutable(chrome);
