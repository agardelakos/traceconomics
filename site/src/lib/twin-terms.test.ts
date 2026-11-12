// The check that keeps the Greek text on the glossary's terms.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  compare,
  loadAllowList,
  loadGlossary,
  loadPairs,
  misses,
  pagePairs,
  visible,
} from "./twin-terms.mjs";

const term = (slug: string, forms: string[]) => ({ slug, term: forms[0], short: "…", forms });
const TERMS = {
  en: [
    term("inflation", ["inflation"]),
    term("annual-rate", ["annual rate", "annual rates"]),
    term("annual-average", ["annual average rate", "annual average rates"]),
    term("quintile", ["income fifth", "income fifths"]),
  ],
  el: [
    term("inflation", ["πληθωρισμός", "πληθωρισμού", "πληθωρισμό"]),
    term("annual-rate", ["ετήσιος ρυθμός", "ετήσιου ρυθμού"]),
    term("annual-average", ["μέσος ετήσιος ρυθμός", "μέσου ετήσιου ρυθμού"]),
    term("quintile", ["πεμπτημόριο", "πεμπτημορίου", "πεμπτημόρια"]),
  ],
};
const pair = (en: string, el: string, id = "i18n:x") => ({ id, en, el });

describe("glossary terms between the English and the Greek", () => {
  it(
    "accepts a Greek twin that uses the term in any form, case or final sigma",
    {
      meta: {
        id: "VT-TWINS-001",
        given:
          "an English text about inflation and its Greek twin with the term inflected, capitalised and ending in a final sigma",
        when: "the pairs are checked from English to Greek",
        then: "no pair misses",
      },
    },
    () => {
      const pairs = [
        pair("Inflation rose.", "Ο ΠΛΗΘΩΡΙΣΜΌΣ ανέβηκε.", "a"),
        pair("The rise in inflation.", "Η άνοδος του πληθωρισμού.", "b"),
        pair("Inflation, again.", "Πληθωρισμός, ξανά.", "c"),
      ];
      expect(misses(pairs, TERMS)).toEqual([]);
    },
  );

  it(
    "reports a Greek twin that says the concept another way",
    {
      meta: {
        id: "VT-TWINS-002",
        given:
          "an English text naming the income fifth, whose Greek twin says «εισοδηματική ομάδα»",
        when: "the pairs are checked from English to Greek",
        then: "the pair is reported once, with its id and the term's slug",
      },
    },
    () => {
      const pairs = [
        pair(
          "Which income fifth are you in? Each income fifth…",
          "Σε ποια εισοδηματική ομάδα ανήκετε;",
          "i18n:income.title",
        ),
      ];
      expect(misses(pairs, TERMS)).toEqual([{ id: "i18n:income.title", term: "quintile" }]);
    },
  );

  it(
    "finds terms as the popovers do: longest form first, whole words only",
    {
      meta: {
        id: "VT-TWINS-003",
        given:
          'an English text with "annual average rate" only, and a Greek twin using «μέσος ετήσιος ρυθμός», plus an English word that merely contains a form',
        when: "the pairs are checked in both directions",
        then: [
          '"annual average rate" does not also count as "annual rate", so nothing misses',
          '"reinflationary" is not a use of "inflation"',
        ],
      },
    },
    () => {
      const pairs = [
        pair("The annual average rate; reinflationary talk.", "Ο μέσος ετήσιος ρυθμός."),
      ];
      expect(misses(pairs, TERMS)).toEqual([]);
      expect(misses(pairs, TERMS, "el")).toEqual([]);
    },
  );

  it(
    "ignores what readers never see: link targets, tags, code and placeholders",
    {
      meta: {
        id: "VT-TWINS-004",
        given:
          'texts where "inflation" appears only in a link\'s address, an HTML attribute, inline code and a placeholder',
        when: "the visible text is taken and the pair is checked",
        then: ["the link's words stay, its address goes", "no term is found, so nothing misses"],
      },
    },
    () => {
      const en =
        'See [the page](/en/glossary/inflation/), <span data-x="inflation">here</span>, `inflation` and {inflation}.';
      expect(visible(en)).not.toContain("inflation");
      expect(visible(en)).toContain("[the page]");
      expect(misses([pair(en, "Δείτε τη σελίδα.")], TERMS)).toEqual([]);
    },
  );

  it(
    "pairs a content page by its shown fields and by section",
    {
      meta: {
        id: "VT-TWINS-005",
        given:
          "an English and a Greek page with the same headings, a title, a glossary-style forms field and two headings that share a slug",
        when: "the page is split into pairs",
        then: [
          "the title, the text before the first heading and each section become pairs, in order",
          "the forms field is not a pair, since it holds the term itself",
          'a second heading with the same slug gets "-2"',
        ],
      },
    },
    () => {
      const en =
        '---\ntitle: "Inflation"\nforms: ["inflation"]\n---\nIntro.\n\n## How much\nA.\n\n## How much\nB.\n';
      const el =
        '---\ntitle: "Πληθωρισμός"\nforms: ["πληθωρισμός"]\n---\nΕισαγωγή.\n\n## Πόσο\nΑ.\n\n## Πόσο\nΒ.\n';
      const ids = pagePairs("method/x.md", en, el).map((p) => p.id);
      expect(ids).toEqual([
        "method/x.md#title",
        "method/x.md#intro",
        "method/x.md#how-much",
        "method/x.md#how-much-2",
      ]);
      const third = pagePairs("method/x.md", en, el)[3];
      expect(third.en).toContain("B.");
      expect(third.el).toContain("Β.");
    },
  );

  it(
    "pairs a page whole when its headings differ in number",
    {
      meta: {
        id: "VT-TWINS-006",
        given:
          "an English page with two headings whose Greek twin has one, the term only in the English second section and the Greek first",
        when: "the page is split into pairs and checked",
        then: ['the body is one pair, "#all"', "the term is found in both, so nothing misses"],
      },
    },
    () => {
      const en = "## One\nText.\n\n## Two\nInflation.\n";
      const el = "## Ένα\nΠληθωρισμός.\n";
      const pairs = pagePairs("pages/x.md", en, el);
      expect(pairs.map((p) => p.id)).toEqual(["pages/x.md#all"]);
      expect(misses(pairs, TERMS)).toEqual([]);
    },
  );

  it(
    "lists Greek terms the English lacks when asked for that direction",
    {
      meta: {
        id: "VT-TWINS-007",
        given: 'a Greek twin that names the annual rate where the English says only "the rate"',
        when: "the pairs are checked from English to Greek, then from Greek to English",
        then: [
          "English to Greek: nothing misses",
          "Greek to English: the pair is listed under the annual rate",
        ],
      },
    },
    () => {
      const pairs = [pair("The rate rose.", "Ο ετήσιος ρυθμός ανέβηκε.")];
      expect(misses(pairs, TERMS)).toEqual([]);
      expect(misses(pairs, TERMS, "el")).toEqual([{ id: "i18n:x", term: "annual-rate" }]);
    },
  );

  it(
    "lets the allow-list only shrink: new misses and stale entries both fail",
    {
      meta: {
        id: "VT-TWINS-008",
        given: "today's misses a and b, and an allow-list holding a and c",
        when: "they are compared",
        then: [
          "b is fresh: a miss not on the list",
          "c is stale: an entry that no longer misses",
          "a, still missing and listed, is neither",
        ],
      },
    },
    () => {
      const a = { id: "i18n:a", term: "gap" };
      const b = { id: "i18n:b", term: "gap" };
      const c = { id: "i18n:c", term: "quintile" };
      expect(compare([a, b], [a, c])).toEqual({ fresh: [b], stale: [c] });
    },
  );
});

/** A made-up site source folder: each [relative path, text] written under a new temporary folder. */
function srcDir(files: [string, string][]): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "twin-terms-"));
  for (const [rel, text] of files) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  }
  return root;
}

describe("the check's files", () => {
  it(
    "pairs every interface string and content page that has a Greek twin, in a fixed order",
    {
      meta: {
        id: "VT-TWINS-009",
        given: [
          "interface strings b and a in both languages, c in English only, and d whose Greek is not a string",
          "a method page with a Greek twin, a method page without one, a non-Markdown file, and a folder of Greek pages with no English folder",
          "a glossary page with its twin, in a folder sorted before method",
        ],
        when: "the folder's pairs are loaded",
        then: [
          "the interface strings come first, sorted by key, only those with a Greek string",
          "then the content pages, folder by folder and file by file in sorted order, each split into its title and sections",
          "a page without a twin, a non-Markdown file and the folder without English give no pairs",
        ],
      },
    },
    () => {
      const page = (title: string, intro: string, heading: string, text: string) =>
        `---\ntitle: "${title}"\n---\n${intro}\n## ${heading}\n${text}\n`;
      const dir = srcDir([
        ["i18n/en.json", JSON.stringify({ b: "B", a: "A", c: "C", d: "D" })],
        ["i18n/el.json", JSON.stringify({ a: "Α", b: "Β", d: { not: "a string" } })],
        ["content/method/en/prices.md", page("Prices", "Intro.", "How", "Text.")],
        ["content/method/el/prices.md", page("Τιμές", "Εισαγωγή.", "Πώς", "Κείμενο.")],
        ["content/method/en/alone.md", page("Alone", "", "X", "")],
        ["content/method/en/notes.txt", "not a page"],
        ["content/method/el/notes.txt", "not a page"],
        ["content/other/el/x.md", page("Χ", "", "Χ", "")],
        ["content/glossary/en/rate.md", '---\nterm: "Rate"\nshort: "A change."\n---\nBody.\n'],
        [
          "content/glossary/el/rate.md",
          '---\nterm: "Ρυθμός"\nshort: "Μια μεταβολή."\n---\nΣώμα.\n',
        ],
      ]);
      const pairs = loadPairs(dir);
      expect(pairs.map((x: { id: string }) => x.id)).toEqual([
        "i18n:a",
        "i18n:b",
        "glossary/rate.md#term",
        "glossary/rate.md#short",
        "glossary/rate.md#intro",
        "method/prices.md#title",
        "method/prices.md#intro",
        "method/prices.md#how",
      ]);
      expect(pairs[0]).toEqual({ id: "i18n:a", en: "A", el: "Α" });
      expect(pairs.at(-1)).toEqual({
        id: "method/prices.md#how",
        en: "## How\nText.\n",
        el: "## Πώς\nΚείμενο.\n",
      });
    },
  );

  it(
    "loads both languages' glossary terms and the allow-list's entries",
    {
      meta: {
        id: "VT-TWINS-010",
        given: [
          "a glossary with one term in English and one in Greek",
          "an allow-list file with one entry, and one with no entries field",
        ],
        when: "the glossary and each allow-list are loaded",
        then: [
          "the glossary holds each language's term under its language",
          "the first allow-list gives its entry, the second an empty list",
        ],
      },
    },
    () => {
      const dir = srcDir([
        [
          "content/glossary/en/rate.md",
          '---\nterm: "Rate"\nforms: ["rate"]\nshort: "A change."\n---\n',
        ],
        [
          "content/glossary/el/rate.md",
          '---\nterm: "Ρυθμός"\nforms: ["ρυθμός"]\nshort: "Μια μεταβολή."\n---\n',
        ],
        ["listed.json", JSON.stringify({ about: "…", entries: [{ id: "i18n:a", term: "rate" }] })],
        ["empty.json", JSON.stringify({ about: "…" })],
      ]);
      const terms = loadGlossary(dir);
      expect(terms.en.map((t: { slug: string; term: string }) => [t.slug, t.term])).toEqual([
        ["rate", "Rate"],
      ]);
      expect(terms.el.map((t: { slug: string; term: string }) => [t.slug, t.term])).toEqual([
        ["rate", "Ρυθμός"],
      ]);
      expect(loadAllowList(path.join(dir, "listed.json"))).toEqual([
        { id: "i18n:a", term: "rate" },
      ]);
      expect(loadAllowList(path.join(dir, "empty.json"))).toEqual([]);
    },
  );
});
