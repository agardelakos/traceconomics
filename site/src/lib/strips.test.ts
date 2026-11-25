import { describe, expect, it } from "vitest";
import { markCurrent, SOURCES, stripFor, stripKey } from "./strips";
import { TOPICS } from "./topics";

const M5 = "official-figures-consistency";
const ROWS = [
  { href: "/en/gr/t/checks/a/", label: "A" },
  { href: "/en/gr/t/checks/ab/", label: "AB" },
];

describe("the bar's third row (strips)", () => {
  it(
    "has a row for every section declared with pages of its own, and for no other",
    {
      meta: {
        id: "VT-STRIP-001",
        given: "the topics' declared inner sections and the rows in lib/strips.ts",
        when: "the two lists are compared",
        then: [
          "every inner section of a live topic has a row",
          "every row belongs to a declared inner section that is one of its topic's sections",
        ],
      },
    },
    () => {
      const declared = TOPICS.filter((x) => x.status === "live").flatMap((x) =>
        (x.inner ?? []).map((s) => {
          expect(x.sections, `${x.slug}: inner section "${s}" is not a section`).toContain(s);
          return `${x.slug}/${s}`;
        }),
      );
      expect(Object.keys(SOURCES).sort()).toEqual(declared.sort());
    },
  );

  it(
    "is built only for a page inside a declared section, and refuses a page inside any other",
    {
      meta: {
        id: "VT-STRIP-002",
        given: "pages of the consistency topic at a section's own address and inside a section",
        when: "the layout asks which row the page shows",
        then: [
          "a section's own page and the overview show none",
          "a check, a finding and a question show their section's row",
          "a page inside a section with no pages of its own fails with the section named",
        ],
      },
    },
    () => {
      expect(stripKey(M5, "")).toBeUndefined();
      expect(stripKey(M5, "checks")).toBeUndefined();
      expect(stripKey(M5, "checks/x")).toBe(`${M5}/checks`);
      expect(stripKey(M5, "checks/x/finding")).toBe(`${M5}/checks`);
      expect(stripKey(M5, "same-question/x")).toBe(`${M5}/same-question`);
      expect(() => stripKey(M5, "method/x")).toThrow(/inside section "method"/);
      expect(() => stripKey("inflation-by-group", "groups/x")).toThrow(/inside section "groups"/);
    },
  );

  it(
    "marks the page being read, or its parent, and only that",
    {
      meta: {
        id: "VT-STRIP-003",
        given: "a row of two pages whose addresses share a beginning (a/ and ab/)",
        when: "it is marked for one page, for a page below it, and for a page it doesn't list",
        then: [
          "the page itself is marked, not its neighbour",
          "a page below one (a finding) marks its parent (the check)",
          "a page matching no row fails, naming the row and the page",
        ],
      },
    },
    () => {
      const current = (page: string) =>
        markCurrent("Checks", ROWS, page)
          .items.filter((i) => i.current)
          .map((i) => i.label);
      expect(current("/en/gr/t/checks/ab/")).toEqual(["AB"]);
      expect(current("/en/gr/t/checks/a/")).toEqual(["A"]);
      expect(current("/en/gr/t/checks/a/june-2001/")).toEqual(["A"]);
      expect(() => current("/en/gr/t/checks/b/")).toThrow(/"Checks" marks 0 rows current/);
    },
  );

  it(
    "is built for a check's page in each language, from the page's address alone",
    {
      meta: {
        id: "VT-STRIP-004",
        given: "Greece's consistency results",
        when: "the strip is built for the second check's page, and for a finding under it",
        then: [
          "it lists every check, the second marked current, under the checks' label",
          "the finding's strip is the same, its check marked",
        ],
      },
    },
    async () => {
      for (const lang of ["en", "el"] as const) {
        const rows = await SOURCES[`${M5}/checks`].rows(lang, "gr");
        expect(rows.length, "the data have no checks: nothing to check").toBeGreaterThan(1);
        const second = rows[1].href.split("/").at(-2);
        const page = await stripFor(lang, M5, "gr", `checks/${second}`);
        const finding = await stripFor(lang, M5, "gr", `checks/${second}/any-finding`);
        expect(page?.label).toBe(SOURCES[`${M5}/checks`].label(lang));
        expect(page?.items.map((i) => i.href)).toEqual(rows.map((r) => r.href));
        expect(page?.items.filter((i) => i.current).map((i) => i.href)).toEqual([rows[1].href]);
        expect(finding).toEqual(page);
      }
    },
  );
});
