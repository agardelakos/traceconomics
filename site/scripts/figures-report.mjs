// A reading list of the figures typed into the site's text: every pair of texts that quotes a
// number with a unit, grouped by its kind on src/i18n/figures-allow.json, with both texts. The
// site check (scripts/checks.mjs, section 11) enforces the list; this report is for reviewing it,
// for example before a release that revises past months.
//
// Usage (from site/): npm run figures:report [-- --out report.md]
// Writes Markdown to stdout, or to the file given. Reads only the source; no build, no network.

import fs from "node:fs";
import path from "node:path";
import { loadPairs, visible } from "../src/lib/twin-terms.mjs";
import { compare, KINDS, loadAllowList, quoted } from "../src/lib/quoted-figures.mjs";

const site = path.resolve(
  path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")),
  "..",
);
const src = path.join(site, "src");
const args = process.argv.slice(2);
const outAt = args.indexOf("--out");
const out = outAt >= 0 ? args[outAt + 1] : null;

const pairs = loadPairs(src);
const byId = new Map(pairs.map((p) => [p.id, p]));
const found = quoted(pairs);
const allowed = loadAllowList(path.join(src, "i18n", "figures-allow.json"));
const kindOf = new Map(allowed.map((e) => [e.id, e.kind]));
const { fresh, changed } = compare(found, allowed);
const flagged = new Set([...fresh, ...changed].map((f) => f.id));

const quote = (text) =>
  visible(text)
    .trim()
    .split("\n")
    .map((l) => `> ${l}`)
    .join("\n");
const lines = ["# Figures typed into the site's text", ""];
const groups = [
  ["not listed, or changed (the site check fails on these)", (f) => flagged.has(f.id)],
  ...Object.entries(KINDS).map(([k, why]) => [
    `${k}: ${why}`,
    (f) => !flagged.has(f.id) && kindOf.get(f.id) === k,
  ]),
];
for (const [title, take] of groups) {
  const these = found.filter(take);
  lines.push(`## ${title} (${these.length})`, "");
  for (const f of these) {
    const p = byId.get(f.id);
    lines.push(
      `### ${f.id}`,
      "",
      `English: ${f.en.join(", ") || "none"}; Greek: ${f.el.join(", ") || "none"}`,
      "",
    );
    lines.push(quote(p.en), "", quote(p.el), "");
  }
}
const text = lines.join("\n");
if (out) fs.writeFileSync(out, text, "utf-8");
else process.stdout.write(text);
