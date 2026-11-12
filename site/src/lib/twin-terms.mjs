// Keeps the Greek text on the glossary's terms. Every English text has a Greek twin (an interface
// string in i18n/, or a section of a content page); where the English uses a glossary term, the
// Greek twin must use the same term, in one of its Greek forms. One concept said three ways reads
// as three concepts, and official statistics name each concept one fixed way so that figures can
// be compared across publications.
//
// Terms are found exactly as the popovers find them (glossary-terms.mjs): each term's `forms`,
// whole words, ignoring case and the final sigma, longest form first, so "annual average rate"
// never also counts as "annual rate". The glossary is the one list of agreed terms.
//
// Content pages are paired section by section (the text before the first heading, then each
// heading with the text under it), since both languages keep the same headings; a page whose
// headings differ in number is paired whole. Plain JavaScript, like glossary-terms.mjs, so the site
// checks can load it without a build.

import fs from "node:fs";
import path from "node:path";
import yaml from "js-yaml";
import { loadTerms, matcher, norm } from "./glossary-terms.mjs";

// Frontmatter fields a reader sees. `forms` and `other` are left out: they hold the term itself
// in both languages, so they would always match.
const SHOWN = ["term", "short", "title", "summary"];

/** Text with what a reader never sees removed: link targets, HTML tags, code, placeholders. */
export function visible(text) {
  return text
    .replace(/\]\([^)]*\)/g, "]")
    .replace(/<[^>]*>/g, " ")
    .replace(/`[^`]*`/g, " ")
    .replace(/\{[^}]*\}/g, " ");
}

/** A heading as an id: lower case, letters and digits joined by hyphens. */
export function slug(heading) {
  return heading
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-|-$/g, "");
}

/** One Markdown page as [part, text] pairs: its shown frontmatter fields, then its sections. */
export function parts(markdown) {
  const front = markdown.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  const data = front ? (yaml.load(front[1]) ?? {}) : {};
  const out = SHOWN.filter((k) => typeof data[k] === "string").map((k) => [k, data[k]]);
  const body = front ? markdown.slice(front[0].length) : markdown;
  const sections = [{ heading: null, lines: [] }];
  for (const line of body.split(/\r?\n/)) {
    const h = line.match(/^#{1,6}\s+(.*)$/);
    if (h) sections.push({ heading: h[1].trim(), lines: [line] });
    else sections.at(-1).lines.push(line);
  }
  for (const s of sections) out.push([s.heading, s.lines.join("\n")]);
  return out;
}

/**
 * The pairs of one page: [{ id, en, el }]. Ids name the English heading's slug (a second heading
 * with the same slug gets "-2"), "intro" for the text before the first heading, or the field name.
 */
export function pagePairs(id, en, el) {
  const a = parts(en);
  const b = parts(el);
  const bodyA = a.filter(([k]) => !SHOWN.includes(k));
  const bodyB = b.filter(([k]) => !SHOWN.includes(k));
  const out = [];
  for (const [k, text] of a.filter(([k]) => SHOWN.includes(k))) {
    const twin = b.find(([j]) => j === k);
    if (twin) out.push({ id: `${id}#${k}`, en: text, el: twin[1] });
  }
  if (bodyA.length !== bodyB.length) {
    out.push({
      id: `${id}#all`,
      en: bodyA.map(([, t]) => t).join("\n"),
      el: bodyB.map(([, t]) => t).join("\n"),
    });
    return out;
  }
  const seen = new Map();
  bodyA.forEach(([heading, text], i) => {
    let s = heading === null ? "intro" : slug(heading) || "section";
    const n = (seen.get(s) ?? 0) + 1;
    seen.set(s, n);
    if (n > 1) s = `${s}-${n}`;
    out.push({ id: `${id}#${s}`, en: text, el: bodyB[i][1] });
  });
  return out;
}

/** Every English/Greek pair of the site: interface strings, then content pages, in a fixed order. */
export function loadPairs(srcDir) {
  const out = [];
  const en = JSON.parse(fs.readFileSync(path.join(srcDir, "i18n", "en.json"), "utf-8"));
  const el = JSON.parse(fs.readFileSync(path.join(srcDir, "i18n", "el.json"), "utf-8"));
  for (const k of Object.keys(en).sort())
    if (typeof el[k] === "string") out.push({ id: `i18n:${k}`, en: en[k], el: el[k] });
  const content = path.join(srcDir, "content");
  for (const kind of fs.readdirSync(content).sort()) {
    const dir = path.join(content, kind, "en");
    if (!fs.existsSync(dir)) continue;
    for (const name of fs.readdirSync(dir).sort()) {
      const twin = path.join(content, kind, "el", name);
      if (!name.endsWith(".md") || !fs.existsSync(twin)) continue;
      out.push(
        ...pagePairs(
          `${kind}/${name}`,
          fs.readFileSync(path.join(dir, name), "utf-8"),
          fs.readFileSync(twin, "utf-8"),
        ),
      );
    }
  }
  return out;
}

/** The slugs of the terms a text uses. */
export function termsIn(text, m) {
  const found = new Set();
  for (const hit of visible(text).matchAll(m.re)) {
    const t = m.owner.get(norm(hit[0]));
    if (t) found.add(t.slug);
  }
  return found;
}

/**
 * The pairs where the `from` language uses a term and its twin uses none of that term's forms:
 * [{ id, term }], in pair order then term order. `from` and `to` are "en" or "el"; `terms` holds
 * both languages' glossary terms ({ en, el }).
 */
export function misses(pairs, terms, from = "en", to = from === "en" ? "el" : "en") {
  const mFrom = matcher(terms[from]);
  const mTo = matcher(terms[to]);
  const known = new Set(terms[to].map((t) => t.slug));
  const out = [];
  for (const p of pairs) {
    const there = termsIn(p[to], mTo);
    for (const term of [...termsIn(p[from], mFrom)].sort()) {
      if (known.has(term) && !there.has(term)) out.push({ id: p.id, term });
    }
  }
  return out;
}

/** Both languages' glossary terms. */
export function loadGlossary(srcDir) {
  const dir = path.join(srcDir, "content", "glossary");
  return { en: loadTerms(dir, "en"), el: loadTerms(dir, "el") };
}

const key = (m) => `${m.id} ${m.term}`;

/**
 * Today's misses against the allow-list: `fresh` are misses not on it (the check fails), `stale`
 * are entries that no longer miss (the check fails too, so the list can only shrink).
 */
export function compare(found, allowed) {
  const allow = new Set(allowed.map(key));
  const now = new Set(found.map(key));
  return {
    fresh: found.filter((m) => !allow.has(key(m))),
    stale: allowed.filter((m) => !now.has(key(m))),
  };
}

/** The allow-list file: { entries: [{ id, term }] }. */
export function loadAllowList(file) {
  const data = JSON.parse(fs.readFileSync(file, "utf-8"));
  return data.entries ?? [];
}
