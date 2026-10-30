// Checks on the source and on the built site (dist/), run after `astro build`. Any failure exits 1.
//
//  1. Text: both languages have the same keys; every content page exists in both languages, and
//     each glossary term sits in the same category in both.
//  2. Sources: every source key in the content exists in the bibliography.
//  3. Nothing private or internal in the built pages: no decision numbers ("D45"), no links to
//     the private notes ("docs/"), no local paths, no e-mail addresses.
//  4. Security: no inline scripts (but JSON-LD data blocks, which browsers never run); scripts, styles, fonts and images only from this site, except the
//     visit-count beacon in release builds: that exact file, once per page, with the site's token.
//  5. Budgets: each page's HTML, CSS and scripts at most 300 KB compressed; any file at most
//     20 MiB; at most 20,000 files (the hosts' limits).
//  6. Links: every link to a page or file of this site leads to one that was built, and every page
//     but the root lives under a language (/el/ or /en/), so addresses stay stable.
//  7. For search engines and AI tools: every page names itself as canonical, at its full address;
//     the sitemap lists exactly the pages in the offered languages; robots.txt names the sitemap;
//     every link of this site in llms.txt leads to a page or file that was built, and it links every
//     topic's page for each country and every country's data page (it is written by hand, so a new
//     topic or country fails here until it is described there).

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, relative, dirname, resolve, extname } from "node:path";
import { gzipSync } from "node:zlib";
import { BEACON, TOKEN } from "../src/lib/analytics.ts";

const site = resolve(dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..");
const dist = join(site, "dist");
const failures = [];
const fail = (msg) => failures.push(msg);

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((d) => (d.isDirectory() ? walk(join(dir, d.name)) : [join(dir, d.name)]));
}

// 1. Text.
const el = JSON.parse(readFileSync(join(site, "src/i18n/el.json"), "utf-8"));
const en = JSON.parse(readFileSync(join(site, "src/i18n/en.json"), "utf-8"));
for (const k of Object.keys(el)) if (!(k in en)) fail(`text key only in Greek: ${k}`);
for (const k of Object.keys(en)) if (!(k in el)) fail(`text key only in English: ${k}`);
for (const [k, v] of Object.entries(el)) if (!v.trim()) fail(`empty Greek text: ${k}`);
for (const [k, v] of Object.entries(en)) if (!v.trim()) fail(`empty English text: ${k}`);
const content = join(site, "src/content");
for (const collection of readdirSync(content)) {
  const names = (lang) => new Set(readdirSync(join(content, collection, lang)).filter((f) => f.endsWith(".md")));
  const a = names("el");
  const b = names("en");
  for (const f of a) if (!b.has(f)) fail(`${collection}/${f}: Greek only`);
  for (const f of b) if (!a.has(f)) fail(`${collection}/${f}: English only`);
}

// The root page's redirect script offers the same languages as the site.
const offered = JSON.parse(readFileSync(join(site, "src/i18n/languages.json"), "utf-8")).offered;
const langJs = readFileSync(join(site, "public/lang.js"), "utf-8").match(/var SITE = (\[[^\]]*\])/);
if (!langJs || JSON.stringify(JSON.parse(langJs[1])) !== JSON.stringify(offered)) fail(`public/lang.js: SITE isn't ${JSON.stringify(offered)}`);

// A glossary term sits in the same category in both languages.
const category = (lang, f) => readFileSync(join(content, "glossary", lang, f), "utf-8").match(/^category:\s*(\S+)/m)?.[1];
for (const f of readdirSync(join(content, "glossary", "en")).filter((f) => f.endsWith(".md"))) {
  if (existsSync(join(content, "glossary", "el", f)) && category("en", f) !== category("el", f)) fail(`glossary/${f}: a different category in Greek and English`);
}

// 2. Sources.
const refsFile = join(site, "public/data/v1/references.json");
if (!existsSync(refsFile)) fail("no public/data/v1/references.json: run the export first");
else {
  const refs = JSON.parse(readFileSync(refsFile, "utf-8")).references;
  for (const file of walk(content).filter((f) => f.endsWith(".md"))) {
    const m = readFileSync(file, "utf-8").match(/^sources:\s*\[(.*?)\]/m);
    for (const key of (m?.[1] ?? "").split(",").map((s) => s.trim()).filter(Boolean)) {
      if (!refs[key]) fail(`${relative(site, file)}: unknown source ${key}`);
    }
  }
}

// The public address, as the Astro config sets it.
const SITE = readFileSync(join(site, "astro.config.mjs"), "utf-8").match(/^\s*site:\s*"([^"]+)"/m)?.[1];
if (!SITE) fail("astro.config.mjs: no site address");
// A full address on this site, as a path into dist/ (null for another site's).
const own = (url) => (SITE && url.startsWith(`${SITE}/`) ? decodeURIComponent(new URL(url).pathname) : null);
const built = (p) => existsSync(p.endsWith("/") ? join(dist, p, "index.html") : join(dist, p));

// 3–5 on the built site.
if (!existsSync(dist)) fail("no dist/: run the build first");
else {
  const files = walk(dist);
  if (files.length > 20000) fail(`${files.length} files in the site, over 20,000`);
  for (const f of files) if (statSync(f).size > 20 * 1024 * 1024) fail(`${relative(dist, f)}: over 20 MiB`);
  const gz = (f) => gzipSync(readFileSync(f)).length;
  const local = (url) => url.startsWith("/") && !url.startsWith("//");
  const jsImports = (file, seen) => {
    if (seen.has(file) || !existsSync(file)) return;
    seen.add(file);
    const text = readFileSync(file, "utf-8");
    for (const m of text.matchAll(/(?:from|import)\s*["'](\.{1,2}\/[^"']+\.js)["']/g)) jsImports(resolve(dirname(file), m[1]), seen);
  };
  const sizes = [];
  const pages = [];
  for (const page of files.filter((f) => f.endsWith(".html"))) {
    const html = readFileSync(page, "utf-8");
    const name = relative(dist, page);
    // No inline scripts: every script is a file, so a strict Content Security Policy can be set.
    // Read tags as browsers do (any case, anything after the end tag's name): an inline <SCRIPT> must not slip past.
    // A JSON-LD block is data, never run (the policy's script rule doesn't apply to it), so it may
    // be inline, if it is exactly that: the one type and valid JSON. Its text is checked below too.
    const ldText = [];
    for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\b[^>]*>/gi)) {
      if (/\bsrc=/.test(m[1]) || !m[2].trim()) continue;
      if (!/^\s*type="application\/ld\+json"\s*$/.test(m[1])) { fail(`${name}: inline script`); continue; }
      try { JSON.parse(m[2]); ldText.push(m[2]); } catch { fail(`${name}: a JSON-LD block that isn't valid JSON`); }
    }
    for (const m of html.matchAll(/<style\b/gi)) fail(`${name}: inline style block`);
    // Resources only from this site (links to sources may point anywhere), but for the beacon.
    let beacons = 0;
    for (const m of html.matchAll(/<(script|link|img|source|iframe)\b[^>]*\b(src|href)="([^"]+)"/g)) {
      const [, tag, , url] = m;
      if (tag === "link" && !/rel="(stylesheet|icon|modulepreload|preload)"/.test(m[0])) continue;
      if (tag === "script" && url === BEACON) {
        beacons += 1;
        const tagText = html.slice(m.index, html.indexOf(">", m.index + m[0].length) + 1);
        const config = tagText.match(/\bdata-cf-beacon="([^"]*)"/)?.[1].replaceAll("&quot;", '"').replaceAll("&#34;", '"');
        if (config !== JSON.stringify({ token: TOKEN })) fail(`${name}: the beacon without the site's token`);
        continue;
      }
      if (!local(url)) fail(`${name}: ${tag} from ${url}`);
    }
    if (beacons > 1) fail(`${name}: the beacon ${beacons} times`);
    // Nothing private or internal in the text.
    const text = html.replace(/<script\b[\s\S]*?<\/script\b[^>]*>/gi, "").replace(/data-config="[^"]*"/g, "") + ldText.join("\n");
    for (const [re, what] of [[/\bD\d{2,3}\b/, "a decision number"], [/\bdocs\//, "a link to private notes"],
      [/[A-Za-z]:\\\\?Users|\/home\/|\/Users\//, "a local path"], [/[\w.+-]+@[\w-]+\.[\w.]+/, "an e-mail address"]]) {
      const hit = text.match(re);
      if (hit) fail(`${name}: ${what} ("${hit[0]}")`);
    }
    // Links to this site's own pages and files lead somewhere.
    for (const m of html.matchAll(/<a\b[^>]*\bhref="([^"#?]*)[^"]*"/g)) {
      const url = m[1];
      if (!local(url)) continue;
      const target = join(dist, decodeURIComponent(url));
      if (!existsSync(url.endsWith("/") ? join(target, "index.html") : target)) fail(`${name}: link to missing ${url}`);
    }
    // Its canonical address is its own, in full; its language twins were built.
    const path = `/${name.replaceAll("\\", "/").replace(/(^|\/)index\.html$/, "$1")}`;
    const canonicals = [...html.matchAll(/<link\b[^>]*\brel="canonical"[^>]*\bhref="([^"]+)"/g)].map((m) => m[1]);
    if (name !== "index.html" && (canonicals.length !== 1 || canonicals[0] !== `${SITE}${path}`)) fail(`${name}: canonical ${canonicals.join(", ") || "missing"}, not ${SITE}${path}`);
    for (const m of html.matchAll(/<link\b[^>]*\brel="alternate"[^>]*\bhref="([^"]+)"/g)) {
      const p = own(m[1]);
      if (p === null) fail(`${name}: an alternate link that isn't a full address on this site (${m[1]})`);
      else if (!built(p)) fail(`${name}: alternate link to missing ${m[1]}`);
    }
    if (/^(el|en)\//.test(name.replaceAll("\\", "/"))) pages.push(path);
    // Every id once per page: popovers and labels find their element by id.
    const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
    const dup = ids.find((id, i) => ids.indexOf(id) !== i);
    if (dup) fail(`${name}: the id "${dup}" is used twice`);
    if (name !== "index.html" && !/^(el|en)\//.test(name.replaceAll("\\", "/")) && !name.startsWith("404")) fail(`${name}: a page outside /el/ and /en/`);
    // Budget: HTML, CSS and scripts (with their imports), compressed.
    const seen = new Set();
    let bytes = gz(page);
    for (const m of html.matchAll(/<link\b[^>]*rel="stylesheet"[^>]*href="([^"]+)"/g)) bytes += gz(join(dist, m[1]));
    for (const m of html.matchAll(/<script\b[^>]*src="([^"]+)"/g)) jsImports(join(dist, m[1]), seen);
    for (const f of seen) bytes += gz(f);
    if (bytes > 300 * 1024) fail(`${name}: ${Math.round(bytes / 1024)} KB compressed, over 300 KB`);
    sizes.push([bytes, name]);
  }
  // 7. The sitemap lists every page in an offered language, and nothing else.
  const sitemap = join(dist, "sitemap.xml");
  if (!existsSync(sitemap)) fail("no sitemap.xml");
  else {
    const locs = [...readFileSync(sitemap, "utf-8").matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
    const want = pages.filter((p) => offered.includes(p.split("/")[1])).map((p) => `${SITE}${p}`).sort();
    for (const u of want) if (!locs.includes(u)) fail(`sitemap.xml: ${u} missing`);
    for (const u of locs) if (!want.includes(u)) fail(`sitemap.xml: ${u} isn't a page in an offered language`);
  }
  const robots = join(dist, "robots.txt");
  if (!existsSync(robots) || !readFileSync(robots, "utf-8").includes(`Sitemap: ${SITE}/sitemap.xml`)) fail("robots.txt doesn't name the sitemap");
  const llms = join(dist, "llms.txt");
  if (!existsSync(llms)) fail("no llms.txt");
  else {
    const links = [...readFileSync(llms, "utf-8").matchAll(/\]\((https?:\/\/[^)\s]+)\)/g)].map((m) => m[1]);
    for (const u of links) {
      const p = own(u);
      if (p !== null && !built(p)) fail(`llms.txt: link to missing ${u}`);
    }
    // A topic for one country is /en/{country}/{topic}/; a country's data, /en/data/{country}/.
    const needed = pages.filter((p) => /^\/en\/([a-z]{2}\/[a-z][a-z-]+|data\/[a-z]{2})\/$/.test(p));
    for (const p of needed) if (!links.includes(`${SITE}${p}`)) fail(`llms.txt: no link to ${SITE}${p}: describe it there`);
  }

  sizes.sort((x, y) => y[0] - x[0]);
  console.log("heaviest pages (HTML, CSS, scripts; compressed):", sizes.slice(0, 3).map(([b, n]) => `${n} ${Math.round(b / 1024)} KB`).join(", "));
  console.log(`${files.length} files, ${files.filter((f) => f.endsWith(".html")).length} pages checked`);
}

if (failures.length) {
  for (const f of failures) console.error(`FAIL ${f}`);
  process.exit(1);
}
console.log("All site checks passed.");
