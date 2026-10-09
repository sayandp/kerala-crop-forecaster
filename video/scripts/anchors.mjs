// Section positions (CSS px) on the captured mobile pages, for Remotion's pans.
import { chromium } from "@playwright/test";
import fs from "node:fs";
const BASE = "https://kerala-crop-forecaster.vercel.app";
const b = await chromium.launch({ channel: "chrome" });
const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
const p = await ctx.newPage();
const out = {};
for (const [name, url, sels] of [
  ["m-home", "/", ["#group-cash", "#group-banana", "#group-veg"]],
  ["m-banana", "/crop/banana", ["#today", "#history", "#high", "#markets", "#map"]],
  ["m-small-onion", "/crop/small_onion", ["#today", "#history", "#high", "#markets"]],
]) {
  await p.goto(BASE + url, { waitUntil: "networkidle" });
  await p.mouse.wheel(0, 1); await p.waitForTimeout(1500);
  const h = await p.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y < h; y += 500) { await p.evaluate((v) => scrollTo(0, v), y); await p.waitForTimeout(100); }
  await p.evaluate(() => scrollTo(0, 0)); await p.waitForTimeout(800);
  out[name] = await p.evaluate((ss) => Object.fromEntries(ss.map((s) => [s, Math.round(document.querySelector(s).getBoundingClientRect().top + scrollY)])), sels);
}
fs.writeFileSync("capture/web/anchors.json", JSON.stringify(out, null, 2));
console.log(JSON.stringify(out));
await b.close();
