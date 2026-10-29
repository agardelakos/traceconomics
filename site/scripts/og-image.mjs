// The sharing images: the picture a link to the site shows when it is posted on social media or in
// a chat (1200×630, the size those services expect). One per language, from the site's own texts
// (the home title, the tagline), its fonts and, faint behind the words, the poorest group's real
// price line from the inflation-by-group data. Run again after changing any of those.
//
// Usage (from site/, with the data exported to public/data):
//   node scripts/og-image.mjs
// Writes public/og/{el,en}.png. Uses Playwright's own Chromium (`npx playwright install chromium`).

import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const site = new URL("..", import.meta.url).pathname;
const W = 1200, H = 630;
const DOMAIN = "traceconomics.com";
const ACCENT = "#0d5e6e";

// The fonts as data, so the page needs nothing from outside: Latin and Greek, the weights used.
const font = (family, weight, file) => {
  const data = readFileSync(join(site, "node_modules/@fontsource", file)).toString("base64");
  return `@font-face{font-family:"${family}";font-weight:${weight};src:url(data:font/woff2;base64,${data}) format("woff2");}`;
};
const fonts = ["latin", "greek"].flatMap((s) => [
  font("OgSerif", 600, `source-serif-4/files/source-serif-4-${s}-600-normal.woff2`),
  font("OgSans", 400, `source-sans-3/files/source-sans-3-${s}-400-normal.woff2`),
  font("OgSans", 700, `source-sans-3/files/source-sans-3-${s}-700-normal.woff2`),
]).join("");

// The poorest group's index in the default setting, from January 2021 (as the home page's example).
function line() {
  const dir = join(site, "public/data/v1/gr/m1/latest");
  const { default: setting } = JSON.parse(readFileSync(join(dir, "settings.json"), "utf-8"));
  const s = JSON.parse(readFileSync(join(dir, "series", `${setting}.json`), "utf-8"));
  const index = s.groups["B/Q1"].index;
  let [y, m] = s.start.split("-").map(Number);
  const axis = [];
  for (let p = s.start; p <= s.end; p = `${y}-${String(m).padStart(2, "0")}`) {
    axis.push(p);
    if (++m > 12) { m = 1; y++; }
  }
  const values = index.slice(axis.indexOf("2021-01")).filter((v) => v !== null);
  const lo = Math.min(...values), hi = Math.max(...values);
  return values.map((v, i) => `${((i / (values.length - 1)) * 330).toFixed(1)},${(108 - ((v - lo) / (hi - lo)) * 104).toFixed(1)}`).join(" ");
}

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");

function page(lang, points) {
  const text = JSON.parse(readFileSync(join(site, "src/i18n", `${lang}.json`), "utf-8"));
  const phrases = text["hub.title"].split("\n").map(esc).join("<br>");
  return `<!doctype html><html lang="${lang}"><head><meta charset="utf-8"><style>${fonts}
body{margin:0}
.og{width:${W}px;height:${H}px;box-sizing:border-box;position:relative;overflow:hidden;padding:72px 80px;background:#f7f6f2;color:#1b1b19;font-family:OgSans,sans-serif;display:flex;flex-direction:column;justify-content:space-between}
.line{position:absolute;right:60px;bottom:110px;opacity:.18}
.mark{display:flex;align-items:center;gap:16px;position:relative;font-family:OgSerif,serif;font-weight:600;font-size:36px}
.title{margin:0;position:relative;font-family:OgSerif,serif;font-weight:600;font-size:${lang === "el" ? 68 : 76}px;line-height:1.05;letter-spacing:-.025em}
.foot{display:flex;align-items:center;justify-content:space-between;gap:32px;position:relative;padding-top:20px;border-top:2px solid ${ACCENT};font-size:24px}
.tagline{color:#57564f}.domain{font-weight:700;color:${ACCENT}}
</style></head><body><div class="og">
<svg class="line" width="560" height="190" viewBox="0 0 330 112"><polyline fill="none" stroke="${ACCENT}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="${points}"/></svg>
<div class="mark"><svg width="56" height="56" viewBox="0 0 28 28"><rect x="1" y="1" width="26" height="26" rx="6" fill="none" stroke="${ACCENT}" stroke-width="2"/><path d="M6 19 L11 13 L15 16 L22 8" fill="none" stroke="${ACCENT}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>${esc(text["site.name"])}</div>
<p class="title">${phrases}</p>
<div class="foot"><span class="tagline">${esc(text["site.tagline"])}</span><span class="domain">${DOMAIN}</span></div>
</div></body></html>`;
}

const points = line();
mkdirSync(join(site, "public/og"), { recursive: true });
const browser = await chromium.launch();
for (const lang of ["el", "en"]) {
  const p = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await p.setContent(page(lang, points));
  // Wait for every face, and refuse to write an image in a fallback font.
  const loaded = await p.evaluate(async () => {
    await Promise.all(["600 76px OgSerif", "400 24px OgSans", "700 24px OgSans"].map((f) => document.fonts.load(f, "aΩ")));
    return ["600 76px OgSerif", "400 24px OgSans", "700 24px OgSans"].every((f) => document.fonts.check(f, "aΩ"));
  });
  if (!loaded) throw new Error(`fonts did not load for ${lang}`);
  const out = join(site, "public/og", `${lang}.png`);
  await p.screenshot({ path: out, clip: { x: 0, y: 0, width: W, height: H } });
  console.log(`wrote ${out}`);
}
await browser.close();
