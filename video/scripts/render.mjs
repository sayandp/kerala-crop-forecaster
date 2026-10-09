// Render both demo videos, their thumbnails and one frame grab per section.
//   npm run render                -> out/kerala-crop-{vertical,horizontal}.{mp4,png}, out/frames/*.png
//   node scripts/render.mjs --fonts-only   (copy fonts into capture/ for `remotion studio`)
// Needs the captured footage (npm run capture:web, npm run capture:bot) in capture/.
import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(".");
const CAPTURE = path.join(ROOT, "capture");
const OUT = path.join(ROOT, "out");
const MAX_MB = 50; // WhatsApp limit

// fonts (OFL) live in assets/, the public dir is capture/
fs.mkdirSync(path.join(CAPTURE, "fonts"), { recursive: true });
for (const f of ["NotoSansMalayalam.ttf", "NotoSans.ttf"]) {
  fs.copyFileSync(path.join(ROOT, "assets/fonts", f), path.join(CAPTURE, "fonts", f));
}
if (process.argv.includes("--fonts-only")) process.exit(0);

for (const need of ["web/meta.json", "web/anchors.json", "bot/conversation.json", "web/rec/d-banana.webm"]) {
  if (!fs.existsSync(path.join(CAPTURE, need))) {
    console.error(`missing capture/${need} — run: npm run capture:web && node scripts/anchors.mjs && npm run capture:bot`);
    process.exit(1);
  }
}

const chrome = process.env.REMOTION_CHROME ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const browserExecutable = fs.existsSync(chrome) ? chrome : null;

console.log("bundling…");
const serveUrl = await bundle({ entryPoint: path.join(ROOT, "src/index.ts"), publicDir: CAPTURE });
fs.mkdirSync(path.join(OUT, "frames"), { recursive: true });

const report = [];
for (const [id, name] of [
  ["Vertical", "kerala-crop-vertical"],
  ["Horizontal", "kerala-crop-horizontal"],
]) {
  const comp = await selectComposition({ serveUrl, id, browserExecutable });
  const file = path.join(OUT, `${name}.mp4`);
  let last = -1;
  await renderMedia({
    serveUrl,
    composition: comp,
    codec: "h264",
    crf: 23,
    pixelFormat: "yuv420p",
    imageFormat: "jpeg",
    jpegQuality: 92,
    concurrency: 4,
    outputLocation: file,
    browserExecutable,
    onProgress: ({ progress }) => {
      const p = Math.floor(progress * 10);
      if (p !== last) console.log(`${id}: ${p * 10}%`), (last = p);
    },
  });
  const mb = fs.statSync(file).size / 1e6;

  // one grab per section (60% into it), sections exported by the composition's props
  const sections = comp.props.sections;
  const names = Object.keys(sections);
  for (const [i, s] of names.entries()) {
    const end = i + 1 < names.length ? sections[names[i + 1]] : comp.durationInFrames;
    const frame = Math.round(sections[s] + (end - sections[s]) * 0.6);
    await renderStill({
      serveUrl,
      composition: comp,
      frame,
      output: path.join(OUT, "frames", `${id.toLowerCase()}-${String(i + 1).padStart(2, "0")}-${s}.png`),
      browserExecutable,
    });
  }
  const thumb = await selectComposition({ serveUrl, id: `Thumb${id}`, browserExecutable });
  await renderStill({ serveUrl, composition: thumb, output: path.join(OUT, `${name}.png`), browserExecutable });

  report.push({ file: path.relative(ROOT, file), seconds: comp.durationInFrames / comp.fps, mb: Math.round(mb * 10) / 10 });
  if (mb >= MAX_MB) {
    console.error(`${file} is ${mb.toFixed(1)} MB (limit ${MAX_MB})`);
    process.exitCode = 1;
  }
}
console.table(report);
