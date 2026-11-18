// Figures typed into the site's text. Charts, tables and the calculator are built from each
// release's data files, so they follow every new month and every revision. A figure typed into a
// sentence ("the poorest fifth's annual rate was 4.9%") doesn't: it stays as written until someone
// edits it, in both languages. Once releases go live without a person reading them first, such a
// figure would quietly go wrong.
//
// So every number with a unit (%, points, euros, PPS) in the interface strings and the content
// pages is listed in src/i18n/figures-allow.json, with the kind of figure it is. A figure that
// isn't listed, or no longer matches its entry, fails the site check (scripts/checks.mjs, section
// 11): writing or changing one means looking at it, and an entry that no longer matches any text
// fails too, so the list only shrinks. A figure about "the latest month" has no kind: it belongs in
// a chart, not in a sentence. `npm run figures:report` lists every figure with its text.
//
// Plain JavaScript, like twin-terms.mjs (whose pairs and visible text it reuses), so the site
// checks can load it without a build.

import fs from "node:fs";
import { loadPairs, visible } from "./twin-terms.mjs";

/** The kinds of figure a sentence may quote, and why each is safe to type. */
export const KINDS = {
  illustrative: "a made-up example that explains a method, not a measurement",
  rule: "a fixed number in a definition or a rule (100% of spending, a fifth is 20%, a tolerance)",
  past: "a measured figure for a period that has ended, named in the text; a revision by the publisher can still change it",
  finding: "part of a finding about one publication, worded for the copies it describes",
};

// A number: digits with either decimal mark and thousands separators (a comma, a point or a
// space before a group of three digits, as in "€6 680"), optionally signed (the minus sign may be
// the typographic one). Numbers without a unit (years, counts, ratios such as "0.69 of income")
// aren't figures this check can tell from the rest of the text, so it leaves them alone.
const NUM = String.raw`[-−+]?\d+(?:[ \u00a0\u202f]\d{3}(?!\d))*(?:[.,]\d+)*`;
const UNIT = [
  "%",
  "€",
  String.raw`PPS\b`,
  String.raw`pp\b`,
  "percentage points?",
  String.raw`(?:index )?points?\b`,
  "per cent",
  String.raw`euros?\b`,
  "ευρώ",
  String.raw`ποσοστιαί\p{L}* μονάδ\p{L}*`,
  String.raw`μονάδ\p{L}*`,
  String.raw`π\.μ\.`,
  "τοις εκατό",
].join("|");
// A range ("0.01–0.03 points", "5–10%") is one figure: both ends are typed.
const FIGURE = new RegExp(String.raw`€\s?${NUM}|${NUM}(?:\s?[–-]\s?${NUM})?\s?(?:${UNIT})`, "giu");

/** The figures with a unit in a text, as written (runs of spaces as one), in order. */
export function figuresIn(text) {
  return [...visible(text).matchAll(FIGURE)].map((m) => m[0].replace(/\s+/gu, " "));
}

/** Every English/Greek pair that quotes a figure: [{ id, en: [...], el: [...] }], in pair order. */
export function quoted(pairs) {
  const out = [];
  for (const p of pairs) {
    const en = figuresIn(p.en);
    const el = figuresIn(p.el);
    if (en.length || el.length) out.push({ id: p.id, en, el });
  }
  return out;
}

const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

/**
 * Today's figures against the allow-list. `fresh`: pairs with figures and no entry; `changed`:
 * pairs whose figures differ from their entry's; `stale`: entries whose pair quotes nothing now;
 * `unkinded`: entries without one of the KINDS. Any of them fails the check.
 */
export function compare(found, allowed) {
  const byId = new Map(allowed.map((e) => [e.id, e]));
  const now = new Set(found.map((f) => f.id));
  return {
    fresh: found.filter((f) => !byId.has(f.id)),
    changed: found.filter((f) => {
      const e = byId.get(f.id);
      return e && !(same(e.en ?? [], f.en) && same(e.el ?? [], f.el));
    }),
    stale: allowed.filter((e) => !now.has(e.id)),
    unkinded: allowed.filter((e) => !Object.hasOwn(KINDS, e.kind)),
  };
}

/** The allow-list file: { entries: [{ id, kind, en: [...], el: [...] }] }. */
export function loadAllowList(file) {
  return JSON.parse(fs.readFileSync(file, "utf-8")).entries ?? [];
}

/** The whole site's figures (source folder `src`). */
export function siteFigures(srcDir) {
  return quoted(loadPairs(srcDir));
}
