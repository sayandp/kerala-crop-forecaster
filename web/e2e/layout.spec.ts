import { expect, test, type Locator } from "@playwright/test";

// Crop-page header on narrow phones: the crop name must never run under the "change market"
// button, with the market sheet closed or open (regression: /crop/banana at 390 px, Malayalam).
const CASES = [
  { lang: "ml", prefix: "", button: "വിപണി മാറ്റുക" },
  { lang: "en", prefix: "/en", button: "Change market" },
] as const;
const CROPS = ["banana", "small_onion", "palayankodan", "bitter_gourd"];

async function box(l: Locator) {
  const b = await l.boundingBox();
  expect(b).not.toBeNull();
  return b!;
}

for (const width of [360, 390]) {
  for (const C of CASES) {
    test(`crop header fits at ${width}px (${C.lang})`, async ({ page }, info) => {
      test.skip(info.project.name !== "mobile-light", "viewport set explicitly; one project is enough");
      await page.setViewportSize({ width, height: 800 });
      for (const crop of CROPS) {
        await page.goto(`${C.prefix}/crop/${crop}`);
        const h1 = page.locator("main h1");
        const button = page.getByRole("button", { name: C.button });
        for (const state of ["closed", "open"] as const) {
          if (state === "open") {
            await button.click();
            await expect(page.locator("dialog[open]")).toBeVisible();
          }
          // the heading's text fits inside its own box (no overflow) ...
          const overflow = await h1.evaluate((el) => el.scrollWidth - el.clientWidth);
          expect(overflow, `${crop} ${state}: h1 overflows by ${overflow}px`).toBeLessThanOrEqual(1);
          // ... and that box does not intersect the button's box
          const a = await box(h1);
          const b = await box(button);
          const overlap =
            Math.min(a.x + a.width, b.x + b.width) > Math.max(a.x, b.x) &&
            Math.min(a.y + a.height, b.y + b.height) > Math.max(a.y, b.y);
          expect(overlap, `${crop} ${state}: h1 overlaps the change-market button`).toBe(false);
          // nothing on the page scrolls sideways
          const hscroll = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
          expect(hscroll, `${crop} ${state}: horizontal scroll`).toBeLessThanOrEqual(0);
        }
      }
    });
  }
}
