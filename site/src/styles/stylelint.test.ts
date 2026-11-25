// The site's own Stylelint rules (stylelint.config.mjs), each shown failing on a typed-in value
// and passing on the token, so a rule that stopped matching would fail here rather than let
// values drift again.
import { fileURLToPath } from "node:url";
import stylelint from "stylelint";
import { describe, expect, it } from "vitest";

const SITE = fileURLToPath(new URL("../../", import.meta.url));

async function problems(css: string, file = "src/styles/global.css"): Promise<string[]> {
  const { results } = await stylelint.lint({
    code: css,
    codeFilename: `${SITE}${file}`,
    configFile: `${SITE}stylelint.config.mjs`,
    cwd: SITE,
  });
  return results.flatMap((r) => r.warnings.map((w) => w.rule));
}

describe("the site's Stylelint rules", () => {
  it(
    "refuse spacing typed in, and accept the scale's tokens and arithmetic on them",
    {
      meta: {
        id: "VT-STYLE-001",
        given: "rules setting gap, margin and padding",
        when: "Stylelint checks them",
        then: [
          "6px, 1rem and a calc() with a typed length are each refused",
          "0, auto, one to four space tokens, calc() on tokens and the full-screen chart's max() pass",
        ],
      },
    },
    async () => {
      for (const bad of [
        "gap: 6px",
        "margin-top: 1rem",
        "padding: 0 6px",
        "margin-top: calc(-1 * 8px)",
      ])
        expect(await problems(`a { ${bad}; }`), bad).toContain(
          "declaration-property-value-allowed-list",
        );
      for (const good of [
        "gap: 0",
        "margin: 0 auto",
        "padding: var(--space-half) var(--space-3) var(--space-1) var(--space-2)",
        "margin-top: calc(-1 * var(--space-2))",
        "padding: var(--space-5) max(var(--space-5), calc((100vw - var(--chart-fullscreen-max)) / 2))",
      ])
        expect(await problems(`a { ${good}; }`), good).toEqual([]);
    },
  );

  it(
    "refuse font sizes and weights typed in, and control heights that skipped the token",
    {
      meta: {
        id: "VT-STYLE-002",
        given: "rules setting font-size, font-weight, min-height and height",
        when: "Stylelint checks them",
        then: [
          "a font size in rem or px and a numeric weight are refused; the text and weight tokens pass",
          "a height between 24px and 64px is refused; the control tokens pass, and so does a chart's 260px",
        ],
      },
    },
    async () => {
      for (const bad of ["font-size: 0.9375rem", "font-size: 12px", "font-weight: 600"])
        expect(await problems(`a { ${bad}; }`), bad).toContain(
          "declaration-property-value-allowed-list",
        );
      for (const bad of ["min-height: 40px", "height: 44px", "min-height: 24px", "height: 64px"])
        expect(await problems(`a { ${bad}; }`), bad).toContain(
          "declaration-property-value-disallowed-list",
        );
      for (const good of [
        "font-size: var(--text-sm)",
        "font-weight: var(--weight-semibold)",
        "min-height: var(--control-h)",
        "height: var(--control-h-compact)",
        "min-height: 260px",
      ])
        expect(await problems(`a { ${good}; }`), good).toEqual([]);
    },
  );

  it(
    "refuse colours typed in, except in tokens.css",
    {
      meta: {
        id: "VT-STYLE-003",
        given: "a hex colour, a named colour and an rgb() colour",
        when: "Stylelint checks them in global.css and in tokens.css",
        then: [
          "in global.css each is refused, and a colour token passes",
          "in tokens.css, where the values are typed, the hex and rgb() colours pass",
        ],
      },
    },
    async () => {
      expect(await problems("a { color: #fff; }")).toContain("color-no-hex");
      expect(await problems("a { color: white; }")).toContain("color-named");
      expect(await problems("a { color: rgb(0 0 0 / 0.5); }")).toContain(
        "function-disallowed-list",
      );
      expect(await problems("a { color: var(--color-text); }")).toEqual([]);
      const tokens = ":root { --color-bg: #fff; --shadow: 0 1px 2px rgb(0 0 0 / 0.08); }";
      expect(await problems(tokens, "src/styles/tokens.css")).toEqual([]);
    },
  );

  it(
    "allow only the agreed breakpoints, written as ranges",
    {
      meta: {
        id: "VT-STYLE-004",
        given: "media queries at the agreed widths and at others, in range and min/max form",
        when: "Stylelint checks them",
        then: [
          "860px is refused",
          "min-width / max-width are refused in favour of the range form",
          "(width < 600px) and (width >= 900px) pass",
        ],
      },
    },
    async () => {
      expect(await problems("@media (width >= 860px) { a { color: inherit; } }")).toContain(
        "media-feature-name-value-allowed-list",
      );
      expect(await problems("@media (min-width: 900px) { a { color: inherit; } }")).toContain(
        "media-feature-range-notation",
      );
      for (const good of ["(width < 600px)", "(width >= 900px)"])
        expect(await problems(`@media ${good} { a { color: inherit; } }`), good).toEqual([]);
    },
  );
});
