import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Home + one crop page, Malayalam and English; every project (mobile/desktop x light/dark).
// axe: WCAG 2.1 A/AA must report zero violations. Screenshots -> e2e/screenshots/ (or SHOTS_DIR).
const SHOTS = process.env.SHOTS_DIR ?? "e2e/screenshots";

const LANGS = [
  { lang: "ml", prefix: "", homeTitle: "ഇന്നത്തെ വിളവില", crop: "നേന്ത്രക്കായ" },
  { lang: "en", prefix: "/en", homeTitle: "Today's crop prices", crop: "Nendran banana" },
] as const;

async function settle(page: Page) {
  // Charts load after first paint + idle and only near the viewport: scroll through the page.
  await page.evaluate(async () => {
    for (let y = 0; y < document.body.scrollHeight; y += 500) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(800);
}

async function axe(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const summary = results.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`);
  expect(summary, summary.join("\n")).toEqual([]);
}

for (const L of LANGS) {
  test(`home ${L.lang}`, async ({ page }, info) => {
    await page.goto(`${L.prefix}/`);
    await expect(page.locator("html")).toHaveAttribute("lang", L.lang);
    await expect(page.getByRole("heading", { level: 1, name: L.homeTitle })).toBeVisible();
    await expect(page.locator("main ul > li a[href*='/crop/']")).toHaveCount(5);
    await page.screenshot({ path: `${SHOTS}/${info.project.name}-${L.lang}-home.png` });
    await settle(page);
    await axe(page);
  });

  test(`crop page ${L.lang}`, async ({ page }, info) => {
    await page.goto(`${L.prefix}/crop/banana`);
    await expect(page.getByRole("heading", { level: 1, name: L.crop })).toBeVisible();
    await expect(page.locator("section[aria-labelledby='markets'] table")).toBeVisible();
    await expect(page.locator("a[href*='t.me/keralacropprices_bot?start=alert_banana_']")).toHaveCount(1);
    await page.screenshot({ path: `${SHOTS}/${info.project.name}-${L.lang}-crop.png` });
    await settle(page);
    await axe(page);
    // market sheet opens and lists markets
    await page.getByRole("button", { name: L.lang === "ml" ? "വിപണി മാറ്റുക" : "Change market" }).click();
    await expect(page.locator("dialog[open] a").first()).toBeVisible();
    await axe(page);
  });
}

test("old per-market URL redirects", async ({ page }) => {
  const res = await page.goto("/p/banana/Kayamkulam");
  expect(res?.url()).toContain("/crop/banana/Kayamkulam");
});
