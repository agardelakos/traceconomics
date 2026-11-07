// Accessibility, with axe-core: every kind of page in both languages, at phone and desktop width, in
// light and dark mode, and with each menu open once (axe can't see inside a closed popover). Fails
// on any serious or critical problem (WCAG 2.2 AA rules); lesser ones are listed in the report.
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, gwt, test } from "./helpers";

const M1 = "gr/inflation-by-group/";
const PATHS = ["", "countries/", "topics/", "gr/", "inflation-by-group/", M1, `${M1}explore/`,
  `${M1}explore/?weights_timing=U&price_source=hicp&groups=Q1,Q5,tenure/renter`, `${M1}explore/?groups=Q1,Q5&view=parts`,
  `${M1}calculator/`, `${M1}method/`, `${M1}method/weights-timing/`, `${M1}groups/`, "data/", "data/gr/",
  "glossary/", "glossary/imputed-rent/", "about/"];
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const VIEWPORTS = { phone: { width: 390, height: 844 }, desktop: { width: 1280, height: 900 } };
// The menus, checked open: the header's quick lists on a wide screen, the whole menu on a phone.
const MENUS = { desktop: ["country-menu", "topic-menu"], phone: ["site-menu"] };

async function check(page: Page, where: string) {
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const bad = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const minor = violations.filter((v) => !bad.includes(v));
  const lines = (vs: typeof violations) => vs.map((v) => `${v.id} (${v.impact}): ${v.help}\n    ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join("\n    ")}`);
  if (minor.length) test.info().annotations.push({ type: "a11y note", description: `${where}: ${lines(minor).join("; ")}` });
  expect(lines(bad), `serious accessibility problems on ${where}`).toEqual([]);
}

for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of Object.entries(VIEWPORTS) as [keyof typeof VIEWPORTS, { width: number; height: number }][]) {
    test.describe(`${scheme}, ${name}`, () => {
      test.use({ colorScheme: scheme, viewport });

      for (const lang of ["el", "en"]) {
        for (const p of PATHS) {
          const path = `/${lang}/${p}`;
          test(path, gwt({
            id: "PW-A11Y-001",
            title: "every kind of page passes the accessibility check, in each language, width and colour scheme",
            given: "a page of one of the site's kinds, in a language, at phone or desktop width, in light or dark mode",
            when: ["it is opened", "everything it draws with a script is in place"],
            then: "an accessibility check against the WCAG 2.2 AA rules finds no serious or critical problem",
          }), async ({ page }) => {
            await page.goto(path, { waitUntil: "networkidle" });
            // Script-drawn parts (charts, the calculator's result) are in place once their busy state ends.
            await expect(page.locator('[aria-busy="true"]:visible')).toHaveCount(0);
            await check(page, path);
          });
        }

        test(`/${lang}/ with each menu open`, gwt({
          id: "PW-A11Y-002",
          title: "the home page passes the accessibility check with each header menu open",
          given: "the home page, in a language, at phone or desktop width, in light or dark mode",
          when: "each menu for that width is opened in turn (the header's quick lists on a wide screen, the whole menu on a phone)",
          then: ["each menu opens", "an accessibility check against the WCAG 2.2 AA rules finds no serious or critical problem while it is open",
            "Escape closes it again"],
        }), async ({ page }) => {
          await page.goto(`/${lang}/`, { waitUntil: "networkidle" });
          for (const id of MENUS[name]) {
            await page.locator(`button[popovertarget="${id}"]`).click();
            await expect(page.locator(`#${id}`)).toBeVisible();
            await check(page, `/${lang}/ (${id} open)`);
            await page.keyboard.press("Escape");
            await expect(page.locator(`#${id}`)).toBeHidden();
          }
        });
      }
    });
  }
}
