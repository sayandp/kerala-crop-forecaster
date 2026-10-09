// Capture real footage of the PRODUCTION dashboard with Playwright (local Chrome).
//   node scripts/capture-web.mjs            -> video/capture/web/*
// Mobile (390x844, Malayalam, light): full-page screenshots at DPR 3 with the fixed chrome
// hidden (+ the chrome captured separately) so Remotion can pan smoothly under it.
// Desktop (1440x900, English): scripted screen recordings (light) with slow eased scrolling
// and pauses, plus high-res screenshots (light + dark).
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.BASE_URL ?? "https://kerala-crop-forecaster.vercel.app";
const OUT = path.resolve("capture/web");
fs.mkdirSync(path.join(OUT, "rec"), { recursive: true });

const browser = await chromium.launch({ channel: "chrome" });
const meta = { base: BASE, capturedAt: new Date().toISOString(), shots: {}, recordings: {} };

/** Eased scroll that looks like a person flicking slowly (rAF-driven, ~60 fps). */
async function smoothScroll(page, toY, ms) {
  await page.evaluate(
    ([target, dur]) =>
      new Promise((resolve) => {
        const start = window.scrollY;
        const max = document.documentElement.scrollHeight - window.innerHeight;
        const end = Math.max(0, Math.min(target, max));
        const t0 = performance.now();
        const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
        const step = (now) => {
          const t = Math.min(1, (now - t0) / dur);
          window.scrollTo(0, start + (end - start) * ease(t));
          if (t < 1) requestAnimationFrame(step);
          else resolve();
        };
        requestAnimationFrame(step);
      }),
    [toY, ms],
  );
}

async function scrollTo(page, selector, ms, offset = 90) {
  const y = await page.evaluate(
    ([sel, off]) => {
      const el = document.querySelector(sel);
      return el ? el.getBoundingClientRect().top + window.scrollY - off : 0;
    },
    [selector, offset],
  );
  await smoothScroll(page, y, ms);
}

async function warm(page) {
  // first interaction loads the interactive charts (the site defers Recharts until then)
  await page.mouse.move(200, 300);
  await page.mouse.wheel(0, 1);
  await page.waitForTimeout(1500);
}

async function settleAll(page) {
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y < h; y += 500) {
    await page.evaluate((v) => window.scrollTo(0, v), y);
    await page.waitForTimeout(120);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(1200);
}

const HIDE_CHROME = `header.sticky, nav[aria-label="Tabs"], [role="status"].fixed { visibility: hidden !important; }`;

// ---------------- mobile: Malayalam, light, DPR 3 ----------------
{
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
    colorScheme: "light",
  });
  const page = await ctx.newPage();
  for (const [name, url] of [
    ["m-home", "/"],
    ["m-banana", "/crop/banana"],
    ["m-small-onion", "/crop/small_onion"],
    ["m-accuracy", "/accuracy"],
  ]) {
    await page.goto(BASE + url, { waitUntil: "networkidle" });
    await warm(page);
    await settleAll(page);
    // the fixed chrome, captured at the top of the page
    if (name === "m-home") {
      await page.locator("header.sticky").screenshot({ path: path.join(OUT, "m-chrome-top.png") });
      await page.locator('nav[aria-label="Tabs"]').screenshot({ path: path.join(OUT, "m-chrome-tabs.png") });
    }
    const style = await page.addStyleTag({ content: HIDE_CHROME });
    await page.screenshot({ path: path.join(OUT, `${name}-full.png`), fullPage: true });
    const h = await page.evaluate(() => document.documentElement.scrollHeight);
    meta.shots[`${name}-full`] = { width: 390, height: h, dpr: 3 };
    await style.evaluate((n) => n.remove());
  }
  // market sheet open (bottom sheet over the crop page)
  await page.goto(BASE + "/crop/banana", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "വിപണി മാറ്റുക" }).click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, "m-banana-sheet.png") });
  await ctx.close();
}

// ---------------- desktop: English, screenshots light + dark ----------------
for (const scheme of ["light", "dark"]) {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    colorScheme: scheme,
  });
  const page = await ctx.newPage();
  for (const [name, url] of [
    ["d-home", "/en"],
    ["d-banana", "/en/crop/banana"],
    ["d-small-onion", "/en/crop/small_onion"],
    ["d-accuracy", "/en/accuracy"],
  ]) {
    await page.goto(BASE + url, { waitUntil: "networkidle" });
    await warm(page);
    await settleAll(page);
    await page.screenshot({ path: path.join(OUT, `${name}-${scheme}.png`) });
  }
  await ctx.close();
}

// ---------------- desktop: scripted recordings (light) ----------------
async function record(name, fn) {
  const dir = path.join(OUT, "rec", name);
  fs.rmSync(dir, { recursive: true, force: true });
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    colorScheme: "light",
    recordVideo: { dir, size: { width: 1440, height: 900 } },
  });
  const page = await ctx.newPage();
  const t0 = Date.now();
  await fn(page);
  const ms = Date.now() - t0;
  await ctx.close();
  const file = fs.readdirSync(dir).find((f) => f.endsWith(".webm"));
  fs.renameSync(path.join(dir, file), path.join(OUT, "rec", `${name}.webm`));
  fs.rmSync(dir, { recursive: true, force: true });
  meta.recordings[name] = { seconds: Math.round(ms / 100) / 10 };
}

await record("d-home", async (page) => {
  await page.goto(BASE + "/en", { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);
  await page.mouse.move(700, 450);
  await scrollTo(page, "#group-banana", 2600);
  await page.waitForTimeout(1600);
  await scrollTo(page, "#group-veg", 2600);
  await page.waitForTimeout(1800);
  await smoothScroll(page, 0, 2200);
  await page.waitForTimeout(1200);
});

await record("d-banana", async (page) => {
  await page.goto(BASE + "/en/crop/banana", { waitUntil: "networkidle" });
  await page.waitForTimeout(2200);
  await page.mouse.move(700, 450);
  await page.mouse.wheel(0, 1);
  await scrollTo(page, "#history", 2400);
  await page.waitForTimeout(1500);
  // hover along the chart to show the crosshair tooltip
  const box = await page.locator("section[aria-labelledby='history'] .recharts-surface").first().boundingBox();
  if (box) {
    for (let i = 0; i <= 30; i++) {
      await page.mouse.move(box.x + box.width * (0.15 + 0.8 * (i / 30)), box.y + box.height * 0.5);
      await page.waitForTimeout(45);
    }
  }
  await page.waitForTimeout(800);
  await scrollTo(page, "#high", 2400);
  await page.waitForTimeout(2200);
  await scrollTo(page, "#markets", 2400);
  await page.waitForTimeout(2000);
  await scrollTo(page, "#map", 2400);
  await page.waitForTimeout(2200);
});

await record("d-small-onion", async (page) => {
  await page.goto(BASE + "/en/crop/small_onion", { waitUntil: "networkidle" });
  await page.waitForTimeout(2200);
  await page.mouse.move(700, 450);
  await scrollTo(page, "#high", 2600);
  await page.waitForTimeout(2200);
});

await record("d-accuracy", async (page) => {
  await page.goto(BASE + "/en/accuracy", { waitUntil: "networkidle" });
  await page.waitForTimeout(1800);
  await page.mouse.move(700, 450);
  const h = await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
  await smoothScroll(page, h, 4200);
  await page.waitForTimeout(2200);
});

fs.writeFileSync(path.join(OUT, "meta.json"), JSON.stringify(meta, null, 2));
await browser.close();
console.log(JSON.stringify(meta, null, 2));
