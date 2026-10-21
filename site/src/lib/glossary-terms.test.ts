// The build step that marks glossary terms in the written pages.
import path from "node:path";
import { describe, expect, it } from "vitest";
import { loadTerms, markTerms, matcher } from "./glossary-terms.mjs";

type Node = { type: string; tagName?: string; value?: string; properties?: Record<string, unknown>; children?: Node[] };
const p = (...children: Node[]): Node => ({ type: "element", tagName: "p", properties: {}, children });
const h2 = (...children: Node[]): Node => ({ type: "element", tagName: "h2", properties: {}, children });
const a = (...children: Node[]): Node => ({ type: "element", tagName: "a", properties: { href: "/x/" }, children });
const text = (value: string): Node => ({ type: "text", value });
const root = (...children: Node[]): Node => ({ type: "root", children });

const TERMS = [
  { slug: "inflation", term: "Πληθωρισμός", short: "…", forms: ["πληθωρισμός", "πληθωρισμού", "πληθωρισμό"] },
  { slug: "consumer-price-index", term: "ΔΤΚ", short: "…", forms: ["δείκτης τιμών καταναλωτή", "ΔΤΚ"] },
  { slug: "hicp", term: "ΕνΔΤΚ", short: "…", forms: ["ΕνΔΤΚ"] },
  { slug: "annual-rate", term: "Annual rate", short: "…", forms: ["annual rate"] },
  { slug: "annual-average", term: "Annual average rate", short: "…", forms: ["annual average rate"] },
];
const mark = (tree: Node, self: string | null = null) => markTerms(tree, { lang: "el", terms: TERMS, more: "Περισσότερα", self });
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
  it("finds an inflected Greek form, whatever its case, and only the first mention", () => {
    const tree = root(p(text("Ο Πληθωρισμός ανέβηκε. Η μέτρηση του πληθωρισμού…")));
    expect(mark(tree)).toEqual(["inflation"]);
    expect(labels(tree)).toEqual(["Πληθωρισμός"]);
  });

  it("prefers the longest form and respects word edges in Greek", () => {
    const tree = root(p(text("Ο ΕνΔΤΚ και ο ΔΤΚ; the annual average rate, then the annual rate.")));
    expect(mark(tree)).toEqual(["hicp", "consumer-price-index", "annual-average", "annual-rate"]);
    expect(labels(tree)).toEqual(["ΕνΔΤΚ", "ΔΤΚ", "annual average rate", "annual rate"]);
  });

  it("leaves headings and links alone, then marks the next mention", () => {
    const tree = root(h2(text("Πληθωρισμός")), p(a(text("πληθωρισμός")), text(" και ο πληθωρισμός")));
    expect(mark(tree)).toEqual(["inflation"]);
    expect((tree.children![0].children![0] as Node).type).toBe("text");
  });

  it("doesn't mark a term on its own page", () => {
    expect(mark(root(p(text("πληθωρισμός"))), "inflation")).toEqual([]);
  });

  it("keeps the text around a term", () => {
    const tree = root(p(text("Πριν ΔΤΚ μετά")));
    mark(tree);
    const kids = tree.children![0].children!;
    expect(kids[0].value).toBe("Πριν ");
    expect(kids[2].value).toBe(" μετά");
  });

  it("refuses a form claimed by two terms", () => {
    expect(() => matcher([
      { slug: "a", term: "A", short: "", forms: ["rate"] },
      { slug: "b", term: "B", short: "", forms: ["Rate"] },
    ])).toThrow(/belongs to both/);
  });

  it("loads the real glossary in both languages without clashes", () => {
    const dir = path.resolve("src/content/glossary");
    for (const lang of ["el", "en"]) {
      const terms = loadTerms(dir, lang);
      expect(terms.length).toBeGreaterThan(30);
      for (const t of terms) expect(t.forms.length, `${lang}/${t.slug}`).toBeGreaterThan(0);
      expect(() => matcher(terms)).not.toThrow();
    }
  });
});
