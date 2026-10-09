// Preview stills without rendering the videos:
//   node scripts/stills.mjs Vertical 100 400 900   -> out/preview/Vertical-<frame>.png
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import fs from "node:fs";
import path from "node:path";

const [id, ...frames] = process.argv.slice(2);
const chrome = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const browserExecutable = fs.existsSync(chrome) ? chrome : null;
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts"), publicDir: path.resolve("capture") });
const composition = await selectComposition({ serveUrl, id, browserExecutable });
console.log(id, composition.durationInFrames, "frames", JSON.stringify(composition.props.sections ?? {}));
fs.mkdirSync("out/preview", { recursive: true });
for (const f of frames) {
  await renderStill({ serveUrl, composition, frame: Number(f), output: `out/preview/${id}-${f}.png`, browserExecutable });
}
