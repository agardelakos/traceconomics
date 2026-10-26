// Marks glossary terms in the site's Markdown (glossary, method and other pages) at build time:
// the first mention of each term on a page becomes the same popover as the GlossaryTerm component
// (a one-sentence explanation and a link to the term's page). A term's page doesn't mark itself.
//
// Matching uses each term's `forms` (every form the word takes in text, since Greek inflects),
// whole words only, ignoring case, longest form first ("annual average rate" before "annual
// rate"). Headings, links, code and existing terms are left alone. A form claimed by two terms
// stops the build. Runs as a plugin of Astro's Markdown processor (Sätteri); plain JavaScript,
// because the Astro config loads it before TypeScript is set up.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import yaml from "js-yaml";

const LANGS = ["el", "en"];
const SKIP = new Set(["a", "h1", "h2", "h3", "h4", "h5", "h6", "code", "pre", "button", "script", "style"]);

// Case and the Greek final sigma don't matter when comparing forms.
const norm = (s) => s.toLowerCase().replace(/ς/g, "σ");
const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The terms of one language: slug, name, short text and forms, read from the Markdown files. */
export function loadTerms(dir, lang) {
  const terms = [];
  for (const name of fs.readdirSync(path.join(dir, lang)).sort()) {
    if (!name.endsWith(".md")) continue;
    const text = fs.readFileSync(path.join(dir, lang, name), "utf-8");
    const front = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
    if (!front) throw new Error(`glossary ${lang}/${name}: no frontmatter`);
    const data = yaml.load(front[1]);
    terms.push({ slug: name.slice(0, -3), term: data.term, short: data.short, forms: data.forms ?? [] });
  }
  return terms;
}

/** A matcher for one language: a regular expression over all forms and form -> term. */
export function matcher(terms) {
  const owner = new Map();
  for (const t of terms) {
    for (const f of t.forms) {
      const k = norm(f);
      if (owner.has(k) && owner.get(k).slug !== t.slug) throw new Error(`glossary form "${f}" belongs to both ${owner.get(k).slug} and ${t.slug}`);
      owner.set(k, t);
    }
  }
  const forms = [...owner.keys()].sort((a, b) => b.length - a.length || a.localeCompare(b));
  // Unicode-aware word edges: \b knows only ASCII letters, so it fails on Greek.
  const re = new RegExp(`(?<![\\p{L}\\p{N}])(?:${forms.map(escape).join("|")})(?![\\p{L}\\p{N}])`, "giu");
  return { re, owner };
}

/**
 * Same id scheme as TermPopover (term plus a short code of its label), marked as from Markdown.
 * `doc` names the file when several files share one page (a topic's steps), so their ids differ.
 */
function popoverId(slug, label, doc) {
  let h = 0;
  for (const ch of label) h = (h * 31 + ch.codePointAt(0)) >>> 0;
  return `term-${slug}-${h.toString(36)}-md${doc ? `-${doc}` : ""}`;
}

function popover(t, label, lang, more, doc) {
  const id = popoverId(t.slug, label, doc);
  const el = (tagName, properties, children) => ({ type: "element", tagName, properties, children });
  const text = (value) => ({ type: "text", value });
  return el("span", { className: ["term-wrap"] }, [
    el("button", { type: "button", className: ["term"], popovertarget: id, style: `anchor-name: --${id}` }, [text(label)]),
    el("span", { popover: "", id, className: ["term-popover"], role: "note", style: `position-anchor: --${id}` }, [
      el("strong", {}, [text(t.term)]),
      el("span", {}, [text(t.short)]),
      el("a", { href: `/${lang}/glossary/${t.slug}/` }, [text(more)]),
    ]),
  ]);
}

/**
 * The state for one page: which terms it can mark and which it already has. `self` is the slug
 * of the term whose page this is (never marked).
 */
export function pageState({ lang, terms, more, self = null, doc = null }) {
  return { lang, more, doc, ...matcher(terms), used: new Set(self ? [self] : []), marked: [] };
}

/** One text node's value, split around the first mentions it holds; null when it holds none. */
export function markText(value, state) {
  const out = [];
  let last = 0;
  state.re.lastIndex = 0;
  for (const m of value.matchAll(state.re)) {
    const t = state.owner.get(norm(m[0]));
    if (!t || state.used.has(t.slug)) continue;
    state.used.add(t.slug);
    state.marked.push(t.slug);
    if (m.index > last) out.push({ type: "text", value: value.slice(last, m.index) });
    out.push(popover(t, m[0], state.lang, state.more, state.doc));
    last = m.index + m[0].length;
  }
  if (last === 0) return null;
  if (last < value.length) out.push({ type: "text", value: value.slice(last) });
  return out;
}

const skipped = (el) => el.type === "element" && (SKIP.has(el.tagName) || (el.properties?.className ?? []).includes("term-wrap"));

/** Marks a whole HAST tree in document order (the same rules as the plugin). Returns the slugs marked. */
export function markTerms(tree, opts) {
  const state = pageState(opts);
  const walk = (node) => {
    if (!node.children) return;
    node.children = node.children.flatMap((child) => {
      if (child.type === "element") { if (!skipped(child)) walk(child); return [child]; }
      if (child.type !== "text") return [child];
      return markText(child.value, state) ?? [child];
    });
  };
  walk(tree);
  return state.marked;
}

/**
 * The Sätteri hast plugin, as a factory: called once per document with its file address, so each
 * page starts with no term marked. Files under src/content/<collection>/<lang>/<slug>.md only.
 */
export function glossaryTerms({ contentDir = path.resolve("src/content"), i18nDir = path.resolve("src/i18n") } = {}) {
  const glossaryDir = path.join(contentDir, "glossary");
  const cache = new Map();
  const forLang = (lang) => {
    if (!cache.has(lang)) {
      // The link text, from the same strings as the GlossaryTerm component.
      const more = JSON.parse(fs.readFileSync(path.join(i18nDir, `${lang}.json`), "utf-8"))["glossary.more"];
      cache.set(lang, { terms: loadTerms(glossaryDir, lang), more });
    }
    return cache.get(lang);
  };
  return ({ fileURL }) => {
    if (!fileURL) return null;
    const rel = path.relative(contentDir, fileURLToPath(fileURL));
    const parts = rel.split(path.sep);
    if (rel.startsWith("..") || parts.length !== 3 || !LANGS.includes(parts[1]) || !parts[2].endsWith(".md")) return null;
    const [collection, lang, name] = parts;
    // A topic's steps are several files on one page: each marks its own first mentions, with ids
    // of its own.
    const state = pageState({ lang, ...forLang(lang), self: collection === "glossary" ? name.slice(0, -3) : null,
      doc: collection === "steps" ? name.slice(0, -3) : null });
    return {
      name: "glossary-terms",
      text(node, ctx) {
        for (let p = ctx.parent(node); p && p.type !== "root"; p = ctx.parent(p)) if (skipped(p)) return;
        const out = markText(node.value, state);
        if (out) ctx.replaceNode(node, out);
      },
    };
  };
}
