// The site's UI rules, checked on the sources and on the built pages (site checks 12 and 13).
// Each has a reason the wiki's "Site patterns" page explains; in short:
//
// Sources (.astro files under src/):
// - A `style` attribute only sets custom properties (`--w: 40%`): a value that comes from the
//   data or names an anchor. Anything else is a layout choice made on one element, so it goes in
//   a utility class or a named class, where Stylelint holds it to the tokens.
// - No <style> block: all CSS lives in src/styles/, where Stylelint sees it.
// - No <nav> outside src/components/: navigation comes from components (the bars, Breadcrumb,
//   JumpLinks, CardNav), so it looks and is labelled the same everywhere.
// - The breadcrumb's markup only in components/ui/Breadcrumb.astro.
//
// Built pages: a page inside a section of a topic for one country
// (/{lang}/{country}/{topic}/{section}/{page}/ and deeper) shows the bar's third row, with
// exactly one item marked as the page being read.
//
// Plain JavaScript, like final-n.mjs, so the site checks can load it without a build.

/** The declarations of a style attribute's value, with `${...}` parts read as one value. */
function declarations(value) {
  return value
    .replace(/\$\{[^}]*\}/g, "X")
    .split(";")
    .map((d) => d.trim())
    .filter(Boolean);
}

/**
 * Problems in one .astro source, each a sentence naming what to do instead.
 * `file` is the path from the site's folder (src/...), with forward slashes.
 */
export function sourceProblems(file, text) {
  const found = [];
  const line = (index) => text.slice(0, index).split("\n").length;
  for (const m of text.matchAll(/\sstyle=(?:"([^"]*)"|\{`([^`]*)`\}|\{([^}]*)\})/g)) {
    const value = m[1] ?? m[2];
    if (value === undefined) {
      found.push(
        `${file}:${line(m.index)}: style set from an expression: set custom properties only, in a template (style={\`--w: \${w}\`})`,
      );
      continue;
    }
    const other = declarations(value).filter((d) => !d.startsWith("--"));
    if (other.length)
      found.push(
        `${file}:${line(m.index)}: inline style "${other.join("; ")}": use a utility class or a named class (src/styles/); style may only set custom properties`,
      );
  }
  for (const m of text.matchAll(/<style[\s>]/g))
    found.push(
      `${file}:${line(m.index)}: <style> block: put the CSS in src/styles/, where Stylelint checks it`,
    );
  if (!file.startsWith("src/components/"))
    for (const m of text.matchAll(/<nav[\s>]/g))
      found.push(
        `${file}:${line(m.index)}: <nav> in a page: use a component (Breadcrumb, JumpLinks, CardNav, or a new one in src/components/ui/)`,
      );
  if (file !== "src/components/ui/Breadcrumb.astro")
    for (const m of text.matchAll(/class=["'][^"']*\bbreadcrumb\b/g))
      found.push(
        `${file}:${line(m.index)}: breadcrumb markup: use src/components/ui/Breadcrumb.astro`,
      );
  return found;
}

// /{lang}/{country}/{topic}/{section}/{page}/...: a two-letter country, then at least three more
// parts. Topics across countries (/{lang}/{topic}/...) and the data pages (/{lang}/data/...) have
// a longer first part, so they never match.
const INNER = /^\/[a-z]{2}\/[a-z]{2}\/[a-z0-9-]+\/[a-z0-9-]+\/[^/]+\//;

/** Whether a built page's address is a page inside a section of a topic for one country. */
export function isInnerPage(address) {
  return INNER.test(address);
}

/**
 * Problems with the bar's third row on one built page: none for a page that isn't inside a
 * section; otherwise exactly one strip, with exactly one item marked as the page being read.
 */
export function stripProblems(address, html) {
  if (!isInnerPage(address)) return [];
  const strips = [...html.matchAll(/<nav\b[^>]*\bdata-strip\b[^>]*>([\s\S]*?)<\/nav>/g)];
  if (strips.length !== 1)
    return [
      `${address}: ${strips.length} strips (the bar's third row), not one: declare its section in topics.ts (inner) and lib/strips.ts`,
    ];
  const current = [...strips[0][1].matchAll(/aria-current="page"/g)].length;
  if (current !== 1) return [`${address}: the strip marks ${current} items as this page, not one`];
  return [];
}
