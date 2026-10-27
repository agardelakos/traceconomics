// Visit every built page on a local server and report Content Security Policy violations,
// with the headers from public/_headers applied as the host applies them.
// Usage: npx wrangler dev --port 8788   (in another terminal; serves dist/ as the host does), then  npm run csp
import { createRequire } from "node:module";
import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const siteDir = process.cwd();
const base = process.argv[2] ?? "http://127.0.0.1:8788";
const require = createRequire(join(siteDir, "package.json"));
const { chromium } = require("playwright");

function pages(dir, root = dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) return n === "data" ? [] : pages(p, root);
    return n === "index.html" ? ["/" + relative(root, dir).replaceAll("\\", "/")] : [];
  });
}

const list = pages(join(siteDir, "dist")).map((p) => (p === "/" ? "/" : p + "/").replace("//", "/"));
const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage();
const violations = [];
page.on("console", (m) => { if (/Content Security Policy|Refused to/i.test(m.text())) violations.push(`${page.url()}: ${m.text()}`); });
const first = await page.goto(base + "/en/");
console.log("CSP header:", first.headers()["content-security-policy"] ? "present" : "MISSING");
const data = await page.request.get(base + "/data/v1/gr/m1/latest/metadata.json");
console.log("data CORS header:", data.headers()["access-control-allow-origin"] ?? "MISSING");
for (const path of list) {
  await page.goto(base + path, { waitUntil: "networkidle" });
  // Let the charts draw and the calculator compute.
  await page.waitForTimeout(400);
}
// Interact with the pages that draw on demand.
await page.goto(base + "/en/gr/inflation-by-group/explore/", { waitUntil: "networkidle" });
for (const sel of await page.$$("select")) { const opts = await sel.$$("option"); if (opts.length > 1) await sel.selectOption({ index: 1 }); }
await page.waitForTimeout(800);
console.log(`${list.length} pages visited; violations: ${violations.length}`);
process.exitCode = violations.length ? 1 : 0;
for (const v of violations.slice(0, 20)) console.log("  " + v);
await browser.close();
