// The build step that marks glossary terms in the written pages.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";
import { glossaryTerms, loadTerms, markTerms, matcher } from "./glossary-terms.mjs";

type Node = {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: Node[];
};
const p = (...children: Node[]): Node => ({
  type: "element",
  tagName: "p",
  properties: {},
  children,
});
const h2 = (...children: Node[]): Node => ({
  type: "element",
  tagName: "h2",
  properties: {},
  children,
});
const a = (...children: Node[]): Node => ({
  type: "element",
  tagName: "a",
  properties: { href: "/x/" },
  children,
});
const text = (value: string): Node => ({ type: "text", value });
const root = (...children: Node[]): Node => ({ type: "root", children });

const TERMS = [
  {
    slug: "inflation",
    term: "Πληθωρισμός",
    short: "…",
    forms: ["πληθωρισμός", "πληθωρισμού", "πληθωρισμό"],
  },
  {
    slug: "consumer-price-index",
    term: "ΔΤΚ",
    short: "…",
    forms: ["δείκτης τιμών καταναλωτή", "ΔΤΚ"],
  },
  { slug: "hicp", term: "ΕνΔΤΚ", short: "…", forms: ["ΕνΔΤΚ"] },
  { slug: "annual-rate", term: "Annual rate", short: "…", forms: ["annual rate"] },
  {
    slug: "annual-average",
    term: "Annual average rate",
    short: "…",
    forms: ["annual average rate"],
  },
];
const mark = (tree: Node, self: string | null = null) =>
  markTerms(tree, { lang: "el", terms: TERMS, more: "Περισσότερα", self });
const labels = (tree: Node): string[] => {
  const out: string[] = [];
  const walk = (n: Node) => {
    if (n.tagName === "button") out.push(n.children![0].value!);
    n.children?.forEach(walk);
  };
  walk(tree);
  return out;
};

describe("marking glossary terms", () => {
  it(
    "finds an inflected Greek form, whatever its case, and only the first mention",
    {
      meta: {
        id: "VT-GLOSS-001",
        given: "a Greek paragraph that mentions inflation twice, first capitalised, then inflected",
        when: "glossary terms are marked",
        then: [
          "only inflation is reported",
          "there is one marked term, labelled with the first mention's text as written",
        ],
      },
    },
    () => {
      const tree = root(p(text("Ο Πληθωρισμός ανέβηκε. Η μέτρηση του πληθωρισμού…")));
      expect(mark(tree)).toEqual(["inflation"]);
      expect(labels(tree)).toEqual(["Πληθωρισμός"]);
    },
  );

  it(
    "prefers the longest form and respects word edges in Greek",
    {
      meta: {
        id: "VT-GLOSS-002",
        given: 'a paragraph mentioning ΕνΔΤΚ, ΔΤΚ, "annual average rate" and "annual rate"',
        when: "glossary terms are marked",
        then: [
          "the four terms are reported in the order they are mentioned",
          "each is labelled with its whole longest form",
        ],
      },
    },
    () => {
      const tree = root(
        p(text("Ο ΕνΔΤΚ και ο ΔΤΚ; the annual average rate, then the annual rate.")),
      );
      expect(mark(tree)).toEqual(["hicp", "consumer-price-index", "annual-average", "annual-rate"]);
      expect(labels(tree)).toEqual(["ΕνΔΤΚ", "ΔΤΚ", "annual average rate", "annual rate"]);
    },
  );

  it(
    "leaves headings and links alone, then marks the next mention",
    {
      meta: {
        id: "VT-GLOSS-003",
        given: "a term in a heading, then in a link, then in plain text",
        when: "glossary terms are marked",
        then: [
          "inflation is reported once",
          "the heading's text stays plain text",
          "the link keeps its one plain text child, unchanged",
          "the one marked term is the mention in plain text",
        ],
      },
    },
    () => {
      const tree = root(
        h2(text("Πληθωρισμός")),
        p(a(text("πληθωρισμός")), text(" και ο πληθωρισμός")),
      );
      expect(mark(tree)).toEqual(["inflation"]);
      expect((tree.children![0].children![0] as Node).type).toBe("text");
      expect(tree.children![1].children![0]).toEqual(a(text("πληθωρισμός")));
      expect(labels(tree)).toEqual(["πληθωρισμός"]);
    },
  );

  it(
    "doesn't mark a term on its own page",
    {
      meta: {
        id: "VT-GLOSS-004",
        given: "a paragraph mentioning inflation, on inflation's own glossary page",
        when: "glossary terms are marked",
        then: "no term is reported",
      },
    },
    () => {
      expect(mark(root(p(text("πληθωρισμός"))), "inflation")).toEqual([]);
    },
  );

  it(
    "keeps the text around a term",
    {
      meta: {
        id: "VT-GLOSS-005",
        given: "a paragraph with text before and after a term",
        when: "glossary terms are marked",
        then: "the text before and after the term stays, either side of it",
      },
    },
    () => {
      const tree = root(p(text("Πριν ΔΤΚ μετά")));
      mark(tree);
      const kids = tree.children![0].children!;
      expect(kids[0].value).toBe("Πριν ");
      expect(kids[2].value).toBe(" μετά");
    },
  );

  it(
    "refuses a form claimed by two terms",
    {
      meta: {
        id: "VT-GLOSS-006",
        given: "two terms with the same form, written in different case",
        when: "the matcher is built",
        then: "building it throws an error saying the form belongs to both",
      },
    },
    () => {
      expect(() =>
        matcher([
          { slug: "a", term: "A", short: "", forms: ["rate"] },
          { slug: "b", term: "B", short: "", forms: ["Rate"] },
        ]),
      ).toThrow(/belongs to both/);
    },
  );

  it(
    "loads the real glossary in both languages without clashes",
    {
      meta: {
        id: "VT-GLOSS-007",
        given: "the site's glossary pages",
        when: "its terms are loaded in Greek and in English",
        then: [
          "each language has more than 30 terms",
          "every term has at least one form",
          "a matcher builds from each language's terms without an error",
        ],
      },
    },
    () => {
      const dir = path.resolve("src/content/glossary");
      for (const lang of ["el", "en"]) {
        const terms = loadTerms(dir, lang);
        expect(terms.length).toBeGreaterThan(30);
        for (const t of terms) expect(t.forms.length, `${lang}/${t.slug}`).toBeGreaterThan(0);
        expect(() => matcher(terms)).not.toThrow();
      }
    },
  );
});

// A made-up site folder for the plugin: one glossary term in English and the link text. The
// plugin is handed each Markdown file's address by the processor.
function site(): { contentDir: string; i18nDir: string; url: (rel: string) => URL } {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "glossary-plugin-"));
  const contentDir = path.join(root, "content");
  const i18nDir = path.join(root, "i18n");
  fs.mkdirSync(path.join(contentDir, "glossary", "en"), { recursive: true });
  fs.mkdirSync(i18nDir);
  fs.writeFileSync(
    path.join(contentDir, "glossary", "en", "inflation.md"),
    '---\nterm: "Inflation"\nforms: ["inflation"]\nshort: "Prices rising."\n---\nBody.\n',
  );
  fs.writeFileSync(path.join(i18nDir, "en.json"), JSON.stringify({ "glossary.more": "Read more" }));
  return { contentDir, i18nDir, url: (rel) => pathToFileURL(path.join(contentDir, rel)) };
}

type Plugin = { name: string; text: (node: Node, ctx: unknown) => void };
type Factory = (file: { fileURL?: URL }) => Plugin | null;

// A paragraph's text node as the processor hands it to the plugin: the node, a way up to its
// parents (`inside` first, then the paragraph, then the root), and the call that swaps it for
// the marked nodes. Returns what the plugin swapped in, or null if it left the node alone.
function visit(plugin: Plugin, value: string, inside: Node[] = []): Node[] | null {
  const node = text(value);
  const chain = [node, ...inside, p(), root()];
  const parents = new Map(chain.slice(0, -1).map((n, i) => [n, chain[i + 1]] as [Node, Node]));
  let replaced: Node[] | null = null;
  plugin.text(node, {
    parent: (n: Node) => parents.get(n),
    replaceNode: (_: Node, out: Node[]) => {
      replaced = out;
    },
  });
  return replaced;
}
const buttonId = (out: Node[] | null) =>
  out?.[0].children?.[0].properties?.popovertarget as string | undefined;

describe("the glossary plugin", () => {
  it(
    "runs only on content pages in a site language and marks each term's first mention",
    {
      meta: {
        id: "VT-GLOSS-008",
        given: [
          "a site folder with the term inflation in its English glossary",
          "no file address, a file outside the content folder, a file one level too deep, a file in an unknown language, a file that isn't Markdown, and an English method page",
        ],
        when: "the plugin is asked for each file, and the method page's text nodes are passed through it",
        then: [
          "every file but the method page gets no plugin",
          "a mention inside a link is left as it is",
          "the method page's first mention of inflation becomes a popover with the term, its short text and a link to its page, named by the language's link text",
          "a second mention on the same page is left as it is",
        ],
      },
    },
    () => {
      const s = site();
      const factory = glossaryTerms({ contentDir: s.contentDir, i18nDir: s.i18nDir }) as Factory;
      expect(factory({})).toBeNull();
      expect(
        factory({
          fileURL: pathToFileURL(path.join(s.contentDir, "..", "elsewhere", "en", "x.md")),
        }),
      ).toBeNull();
      expect(factory({ fileURL: s.url("method/en/deeper/x.md") })).toBeNull();
      expect(factory({ fileURL: s.url("method/de/x.md") })).toBeNull();
      expect(factory({ fileURL: s.url("method/en/x.txt") })).toBeNull();

      const plugin = factory({ fileURL: s.url("method/en/prices.md") })!;
      expect(plugin.name).toBe("glossary-terms");
      expect(visit(plugin, "Prices and inflation, again.", [a()])).toBeNull();
      const out = visit(plugin, "Prices and inflation.");
      expect(out?.map((n) => n.type)).toEqual(["text", "element", "text"]);
      const popover = out![1].children![1];
      expect(popover.children!.map((n) => n.children![0].value)).toEqual([
        "Inflation",
        "Prices rising.",
        "Read more",
      ]);
      expect(popover.children![2].properties).toEqual({ href: "/en/glossary/inflation/" });
      expect(visit(plugin, "More inflation.")).toBeNull();
    },
  );

  it(
    "leaves a term's own page unmarked, names steps' popovers by their file and reads each language once",
    {
      meta: {
        id: "VT-GLOSS-009",
        given: "the same site folder, the term's own glossary page and two step files of one topic",
        when: "each page's text naming the term is passed through the plugin, the link text file removed after the first page",
        then: [
          "the term's own page leaves its name unmarked",
          "each step file marks the term, and their popover ids differ only by the step's file name",
          "the pages after the first still mark the term, from the language's files as read the first time",
        ],
      },
    },
    () => {
      const s = site();
      const factory = glossaryTerms({ contentDir: s.contentDir, i18nDir: s.i18nDir }) as Factory;
      const own = factory({ fileURL: s.url("glossary/en/inflation.md") })!;
      fs.rmSync(path.join(s.i18nDir, "en.json"));
      expect(visit(own, "Inflation is the rise in prices.")).toBeNull();
      const one = buttonId(visit(factory({ fileURL: s.url("steps/en/step-1.md") })!, "Inflation."));
      const two = buttonId(visit(factory({ fileURL: s.url("steps/en/step-2.md") })!, "Inflation."));
      expect(one).toMatch(/^term-inflation-[0-9a-z]+-md-step-1$/);
      expect(two).toBe(one!.replace(/step-1$/, "step-2"));
    },
  );
});
