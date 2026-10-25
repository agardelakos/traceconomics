// Accessibility check with axe-core on the built site, in both languages, at phone and desktop
// width, in light and dark mode. Fails on any serious or critical problem; lists the rest.
//
// Usage (with `npm run preview` running):  node scripts/a11y.mjs [base url]
// Uses the installed Chrome, so no browser download is needed.

import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright";

const base = process.argv[2] ?? "http://localhost:4321";
const PATHS = ["", "start/", "explore/", "explore/?weights_timing=U&price_source=hicp&groups=Q1,Q5,tenure/renter", "calculator/",
  "glossary/", "glossary/imputed-rent/", "method/", "method/weights-timing/", "data/", "about/", "changelog/"];
const pages = ["/", ...["el", "en"].flatMap((l) => PATHS.map((p) => `/${l}/${p}`))];

const browser = await chromium.launch({ channel: "chrome" });
let serious = 0;
let minor = 0;
for (const scheme of ["light", "dark"]) {
  for (const [name, width, height] of [["phone", 390, 844], ["desktop", 1280, 900]]) {
    const context = await browser.newContext({ viewport: { width, height }, colorScheme: scheme });
    const page = await context.newPage();
    for (const path of pages) {
      await page.goto(base + path, { waitUntil: "networkidle" });
      if (path === "/") continue;                   // the root page moves on to a language at once
      await page.waitForTimeout(200);
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
      for (const v of result.violations) {
        const bad = v.impact === "serious" || v.impact === "critical";
        if (bad) serious++; else minor++;
        console.log(`${bad ? "FAIL" : "note"} [${scheme} ${name}] ${path}: ${v.id} (${v.impact}) ${v.help}`);
        for (const n of v.nodes.slice(0, 3)) console.log(`      ${n.target.join(" ")}: ${n.failureSummary?.split("\n")[1] ?? ""}`);
      }
    }
    await context.close();
  }
}
await browser.close();
console.log(serious ? `${serious} serious or critical problem(s), ${minor} other(s).` : `No serious or critical problems (${minor} other notes).`);
process.exit(serious ? 1 : 0);
