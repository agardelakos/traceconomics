// The UI rules (site checks 12 and 13): each shown failing on a bad snippet and passing on a good
// one, and the source rules run over the real src/ so a page that breaks one fails without a build.
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { isInnerPage, sourceProblems, stripProblems } from "./ui-rules.mjs";

const SITE = fileURLToPath(new URL("../../", import.meta.url));

function astroFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((d) =>
    d.isDirectory()
      ? astroFiles(join(dir, d.name))
      : d.name.endsWith(".astro")
        ? [join(dir, d.name)]
        : [],
  );
}

const PAGE = "src/pages/[lang]/about.astro";

describe("the UI rules on the sources", () => {
  it(
    "refuse inline styles other than custom properties",
    {
      meta: {
        id: "VT-UIRULES-001",
        given:
          "elements with a style attribute: plain, a template, an expression, custom properties only",
        when: "the source rules read them",
        then: [
          "a plain declaration, a template with a plain declaration and a style set from an expression are each refused, with the line",
          "custom properties, in a plain attribute or a template, pass",
        ],
      },
    },
    () => {
      expect(sourceProblems(PAGE, '<div class="stack" style="gap: 6px">')).toEqual([
        expect.stringMatching(/^src\/pages\/\[lang\]\/about\.astro:1: inline style "gap: 6px"/),
      ]);
      expect(sourceProblems(PAGE, "\n<span style={`width: ${w}%; --c: ${c}`}>")).toEqual([
        expect.stringMatching(/:2: inline style "width: X%"/),
      ]);
      expect(sourceProblems(PAGE, "<span style={styles}>")).toEqual([
        expect.stringMatching(/:1: style set from an expression/),
      ]);
      expect(sourceProblems(PAGE, '<li style="--anchor: --topic-menu">')).toEqual([]);
      expect(sourceProblems(PAGE, "<span style={`--w: ${w}%; --c: ${c}`}>")).toEqual([]);
    },
  );

  it(
    "refuse <style> blocks, <nav> in pages and breadcrumb markup outside its component",
    {
      meta: {
        id: "VT-UIRULES-002",
        given: "a page and components with a <style> block, a <nav> and a breadcrumb's markup",
        when: "the source rules read them",
        then: [
          "a <style> block is refused anywhere, components too",
          "a <nav> is refused in a page and allowed in a component",
          "breadcrumb markup is refused outside components/ui/Breadcrumb.astro and allowed in it",
        ],
      },
    },
    () => {
      const bar = "src/components/CountryBar.astro";
      expect(sourceProblems(bar, "<style>\n.x { gap: 0 }\n</style>")).toEqual([
        expect.stringMatching(/<style> block/),
      ]);
      expect(sourceProblems(PAGE, '<nav aria-label="x">')).toEqual([
        expect.stringMatching(/<nav> in a page/),
      ]);
      expect(sourceProblems(bar, '<nav class="topic-nav">')).toEqual([]);
      expect(sourceProblems(bar, '<p class="small breadcrumb">')).toEqual([
        expect.stringMatching(/breadcrumb markup/),
      ]);
      expect(
        sourceProblems("src/components/ui/Breadcrumb.astro", '<nav class="breadcrumb">'),
      ).toEqual([]);
    },
  );

  it(
    "hold on every .astro file of the site",
    {
      meta: {
        id: "VT-UIRULES-003",
        given: "every .astro file under src/",
        when: "the source rules read each one",
        then: "none has a problem, and there are files to read",
      },
    },
    () => {
      const files = astroFiles(join(SITE, "src"));
      expect(files.length).toBeGreaterThan(30);
      const found = files.flatMap((f) =>
        sourceProblems(relative(SITE, f).split("\\").join("/"), readFileSync(f, "utf-8")),
      );
      expect(found).toEqual([]);
    },
  );
});

describe("the UI rules on the built pages", () => {
  const strip = (items: string) =>
    `<nav class="topic-nav strip" aria-label="Checks" data-strip><ul>${items}</ul></nav>`;
  const ONE = '<li><a href="/en/a/">A</a></li><li><span aria-current="page">B</span></li>';

  it(
    "know which addresses are pages inside a section",
    {
      meta: {
        id: "VT-UIRULES-004",
        given:
          "addresses of a check, a finding, a method option, a section's page, a topic's overview, a topic across countries and a data page",
        when: "each is asked whether it is a page inside a section",
        then: [
          "the check, the finding and the option are",
          "the section's page, the overview, the topic across countries and the data page are not",
        ],
      },
    },
    () => {
      for (const a of [
        "/en/gr/official-figures-consistency/checks/cpi-rates-own-index/",
        "/el/gr/official-figures-consistency/checks/cpi-rates-own-index/june-2001/",
        "/en/gr/inflation-by-group/method/weights-timing/",
      ])
        expect(isInnerPage(a), a).toBe(true);
      for (const a of [
        "/en/gr/inflation-by-group/method/",
        "/en/gr/inflation-by-group/",
        "/en/inflation-by-group/",
        "/en/data/gr/",
      ])
        expect(isInnerPage(a), a).toBe(false);
    },
  );

  it(
    "require one strip with one current item on a page inside a section",
    {
      meta: {
        id: "VT-UIRULES-005",
        given:
          "a page inside a section built without a strip, with two strips, with a strip marking none or two items, and with a correct strip",
        when: "the built-page rule reads each",
        then: [
          "no strip, two strips, none marked and two marked each fail, naming the page",
          "a strip with one item marked passes, and a section's own page needs none",
        ],
      },
    },
    () => {
      const page = "/en/gr/official-figures-consistency/checks/x/";
      expect(stripProblems(page, "<main></main>")).toEqual([expect.stringMatching(/0 strips/)]);
      expect(stripProblems(page, strip(ONE) + strip(ONE))).toEqual([
        expect.stringMatching(/2 strips/),
      ]);
      expect(stripProblems(page, strip('<li><a href="/en/a/">A</a></li>'))).toEqual([
        expect.stringMatching(/marks 0 items/),
      ]);
      expect(
        stripProblems(page, strip(ONE + '<li><span aria-current="page">C</span></li>')),
      ).toEqual([expect.stringMatching(/marks 2 items/)]);
      expect(stripProblems(page, strip(ONE))).toEqual([]);
      expect(stripProblems("/en/gr/official-figures-consistency/checks/", "<main></main>")).toEqual(
        [],
      );
    },
  );
});
