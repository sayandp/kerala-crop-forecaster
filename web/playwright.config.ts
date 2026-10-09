import { defineConfig } from "@playwright/test";

// Smoke + accessibility tests. Run against a local production build (default) or any deployed
// URL:  BASE_URL=https://<preview>.vercel.app pnpm test:e2e
// Uses the installed Chrome (PW_CHANNEL=chrome) so no browser download is needed.
const baseURL = process.env.BASE_URL ?? "http://localhost:3100";
const channel = process.env.PW_CHANNEL ?? "chrome";
// Vercel previews sit behind Deployment Protection: send the automation bypass (never committed).
const bypass = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
const extraHTTPHeaders = bypass ? { "x-vercel-protection-bypass": bypass, "x-vercel-set-bypass-cookie": "true" } : undefined;

const mobile = { viewport: { width: 393, height: 851 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 };
const desktop = { viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 };

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL, channel, extraHTTPHeaders },
  projects: [
    { name: "mobile-light", use: { ...mobile, colorScheme: "light" } },
    { name: "mobile-dark", use: { ...mobile, colorScheme: "dark" } },
    { name: "desktop-light", use: { ...desktop, colorScheme: "light" } },
    { name: "desktop-dark", use: { ...desktop, colorScheme: "dark" } },
  ],
  webServer: process.env.BASE_URL
    ? undefined
    : { command: "npm run start -- -p 3100", url: "http://localhost:3100", reuseExistingServer: true, timeout: 60_000 },
});
