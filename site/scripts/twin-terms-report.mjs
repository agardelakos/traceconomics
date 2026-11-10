// A reading list for whoever reviews the Greek text: every place where one language uses a
// glossary term and its twin doesn't, grouped by term, with both texts side by side. Both
// directions: English → Greek is what the site check enforces (scripts/checks.mjs, section 9);
// Greek → English is listed only, as a pointer to text that may say more than the English.
//
// Usage (from site/): npm run terms:report [-- --out report.md]
// Writes Markdown to stdout, or to the file given. Reads only the source; no build, no network.

import fs from "node:fs";
import path from "node:path";
import { compare, loadAllowList, loadGlossary, loadPairs, misses } from "../src/lib/twin-terms.mjs";

const site = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..");
const src = path.join(site, "src");
const args = process.argv.slice(2);
const outAt = args.indexOf("--out");
const out = outAt >= 0 ? args[outAt + 1] : null;

const pairs = loadPairs(src);
const byId = new Map(pairs.map((p) => [p.id, p]));
const terms = loadGlossary(src);
const names = { en: new Map(terms.en.map((t) => [t.slug, t])), el: new Map(terms.el.map((t) => [t.slug, t])) };
const allowed = loadAllowList(path.join(src, "i18n", "terms-allow.json"));
const { fresh } = compare(misses(pairs, terms), allowed);
const isFresh = new Set(fresh.map((m) => `${m.id} ${m.term}`));

const quote = (text) => text.trim().split("\n").map((l) => `> ${l}`).join("\n");
const lines = [];
const section = (title, from, to, intro) => {
  const found = misses(pairs, terms, from, to);
  lines.push(`## ${title} (${found.length})`, "", intro, "");
  const groups = new Map();
  for (const m of found) groups.set(m.term, [...(groups.get(m.term) ?? []), m]);
  const order = [...groups.keys()].sort((a, b) => groups.get(b).length - groups.get(a).length || a.localeCompare(b));
  for (const slug of order) {
    const t = names[from].get(slug);
    const twin = names[to].get(slug);
    lines.push(`### ${t.term} → ${twin.term} (${groups.get(slug).length})`, "");
    lines.push(`Forms in the ${to === "el" ? "Greek" : "English"} glossary: ${twin.forms.map((f) => `«${f}»`).join(", ")}`, "");
    for (const m of groups.get(slug)) {
      const p = byId.get(m.id);
      const tag = from === "en" ? (isFresh.has(`${m.id} ${m.term}`) ? " (new: fails the check)" : " (on the allow-list)") : "";
      lines.push(`#### \`${m.id}\`${tag}`, "", "EN:", "", quote(p.en), "", "EL:", "", quote(p.el), "");
    }
  }
};

lines.push("# Glossary terms between the English and the Greek", "");
lines.push(`${pairs.length} pairs of texts; ${terms.en.length} glossary terms.`, "");
section("English uses a term, the Greek doesn't", "en", "el",
  "Each one: use the term in the Greek (in any of its forms), add the missing form to the Greek glossary, or, if the English uses the word in another sense, narrow the English forms.");
section("Greek uses a term, the English doesn't", "el", "en",
  "Listed only, never a failure: the Greek may say more than the English, or the English may use another word for the same thing.");

const text = lines.join("\n");
if (out) fs.writeFileSync(out, text, { encoding: "utf-8" });
else process.stdout.write(text);
