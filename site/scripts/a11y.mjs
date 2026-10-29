// Accessibility check with axe-core on the built site, in both languages, at phone and desktop
// width, in light and dark mode, and once more with each menu open (axe can't see a closed
// popover). Fails on any serious or critical problem, and on a page that doesn't load; lists the rest.
//
// Usage (with `npm run preview` running):  node scripts/a11y.mjs [base url]
// Uses the installed Chrome, so no browser download is needed.

import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright";

const base = process.argv[2] ?? "http://localhost:4321";
const M1 = "gr/inflation-by-group/";
const PATHS = ["", "countries/", "topics/", "gr/", "inflation-by-group/", M1, `${M1}explore/`,
  `${M1}explore/?weights_timing=U&price_source=hicp&groups=Q1,Q5,tenure/renter`, `${M1}calculator/`,
  `${M1}method/`, `${M1}method/weights-timing/`, `${M1}groups/`, "data/gr/",
  "glossary/", "glossary/imputed-rent/", "data/", "about/"];
const pages = ["/", ...["el", "en"].flatMap((l) => PATHS.map((p) => `/${l}/${p}`))];
// The menus, checked open: the header's quick lists on a wide screen, the whole menu on a phone.
const MENUS = { desktop: ["country-menu", "topic-menu"], phone: ["site-menu"] };
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

const browser = await chromium.launch({ channel: "chrome" });
let serious = 0;
let minor = 0;
for (const scheme of ["light", "dark"]) {
  for (const [name, width, height] of [["phone", 390, 844], ["desktop", 1280, 900]]) {
    const context = await browser.newContext({ viewport: { width, height }, colorScheme: scheme });
    const page = await context.newPage();
    for (const path of pages) {
      const response = await page.goto(base + path, { waitUntil: "networkidle" });
      if (response && response.status() >= 400) {
        serious++;
        console.log(`FAIL [${scheme} ${name}] ${path}: HTTP ${response.status()}`);
        continue;
      }
      if (path === "/") continue;                   // the root page moves on to a language at once
      await page.waitForTimeout(200);
      report(scheme, name, path, (await new AxeBuilder({ page }).withTags(TAGS).analyze()).violations);
      // Each menu once, open, on one page per language (the header is the same on every page).
      if (!/^\/[a-z]{2}\/$/.test(path)) continue;
      for (const id of MENUS[name]) {
        await page.click(`button[popovertarget="${id}"]`);
        await page.waitForTimeout(150);
        report(scheme, name, `${path} (${id} open)`, (await new AxeBuilder({ page }).withTags(TAGS).analyze()).violations);
        await page.keyboard.press("Escape");
      }
    }
    await context.close();
  }
}
await browser.close();

function report(scheme, name, where, violations) {
  for (const v of violations) {
    const bad = v.impact === "serious" || v.impact === "critical";
    if (bad) serious++; else minor++;
    console.log(`${bad ? "FAIL" : "note"} [${scheme} ${name}] ${where}: ${v.id} (${v.impact}) ${v.help}`);
    for (const n of v.nodes.slice(0, 3)) console.log(`      ${n.target.join(" ")}: ${n.failureSummary?.split("\n")[1] ?? ""}`);
  }
}
console.log(serious ? `${serious} serious or critical problem(s), ${minor} other(s).` : `No serious or critical problems (${minor} other notes).`);
process.exit(serious ? 1 : 0);
