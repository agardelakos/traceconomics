// Screenshots of the built site, for looking at it: each page at phone and desktop width, in
// light and dark mode, with any browser console errors printed.
//
// Usage (with `npm run preview` running):
//   node scripts/shots.mjs <out folder> [base url] [path ...]
// Uses the installed Chrome, so no browser download is needed.

import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const [out, base = "http://localhost:4321", ...paths] = process.argv.slice(2);
if (!out) {
  console.error("usage: node scripts/shots.mjs <out folder> [base url] [path ...]");
  process.exit(2);
}
const pages = paths.length ? paths : ["/el/", "/en/"];
const sizes = [["phone", 390, 844], ["desktop", 1280, 900]];
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ channel: "chrome" });
let errors = 0;
for (const scheme of ["light", "dark"]) {
  for (const [name, width, height] of sizes) {
    const context = await browser.newContext({ viewport: { width, height }, colorScheme: scheme, deviceScaleFactor: 1 });
    const page = await context.newPage();
    page.on("console", (m) => { if (m.type() === "error") { errors++; console.log(`console error on ${page.url()}: ${m.text()}`); } });
    page.on("pageerror", (e) => { errors++; console.log(`page error on ${page.url()}: ${e.message}`); });
    page.on("response", (r) => { if (r.status() >= 400) console.log(`HTTP ${r.status()}: ${r.url()}`); });
    for (const p of pages) {
      await page.goto(base + p, { waitUntil: "networkidle" });
      await page.waitForTimeout(300);
      const file = join(out, `${p.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "root"}_${name}_${scheme}.png`);
      await page.screenshot({ path: file, fullPage: true });
      console.log(file);
    }
    await context.close();
  }
}
await browser.close();
process.exit(errors ? 1 : 0);
