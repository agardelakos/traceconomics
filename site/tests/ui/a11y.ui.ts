// Accessibility, with axe-core: every kind of page in both languages, at phone and desktop width, in
// light and dark mode, and with each menu open once (axe can't see inside a closed popover). Fails
// on any serious or critical problem (WCAG 2.2 AA rules); lesser ones are listed in the report.
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, gwt, test } from "./helpers";

const M1 = "gr/inflation-by-group/";
const M5 = "gr/official-figures-consistency/";
// The consistency topic: its page across countries, Greece's overview and Method, the check cards,
// a check (its tables), a finding, the questions, a question with its chart and one with its source
// popovers and AADE's table as published.
const M5_PATHS = [
  "official-figures-consistency/",
  M5,
  `${M5}method/`,
  `${M5}checks/`,
  `${M5}checks/cpi-rates-own-index/`,
  `${M5}checks/cpi-rates-own-index/june-2001/`,
  `${M5}same-question/`,
  `${M5}same-question/renters/`,
  `${M5}same-question/rent-paid/`,
];

const PATHS = [
  "",
  "countries/",
  "topics/",
  "gr/",
  "inflation-by-group/",
  M1,
  `${M1}explore/`,
  `${M1}explore/?weights_timing=U&price_source=hicp&groups=Q1,Q5,tenure/renter`,
  `${M1}explore/?groups=Q1,Q5&view=parts`,
  `${M1}calculator/`,
  `${M1}method/`,
  `${M1}method/weights-timing/`,
  `${M1}groups/`,
  "data/",
  "data/gr/",
  "glossary/",
  "glossary/imputed-rent/",
  "about/",
  ...M5_PATHS,
];
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const VIEWPORTS = { phone: { width: 390, height: 844 }, desktop: { width: 1280, height: 900 } };
// The menus, checked open: the header's quick lists on a wide screen, the whole menu on a phone.
const MENUS = { desktop: ["country-menu", "topic-menu"], phone: ["site-menu"] };

async function check(page: Page, where: string) {
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const bad = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const minor = violations.filter((v) => !bad.includes(v));
  const lines = (vs: typeof violations) =>
    vs.map(
      (v) =>
        `${v.id} (${v.impact}): ${v.help}\n    ${v.nodes
          .slice(0, 3)
          .map((n) => n.target.join(" "))
          .join("\n    ")}`,
    );
  if (minor.length)
    test
      .info()
      .annotations.push({ type: "a11y note", description: `${where}: ${lines(minor).join("; ")}` });
  expect(lines(bad), `serious accessibility problems on ${where}`).toEqual([]);
}

for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of Object.entries(VIEWPORTS) as [
    keyof typeof VIEWPORTS,
    { width: number; height: number },
  ][]) {
    test.describe(`${scheme}, ${name}`, () => {
      test.use({ colorScheme: scheme, viewport });

      for (const lang of ["el", "en"]) {
        for (const p of PATHS) {
          const path = `/${lang}/${p}`;
          test(
            path,
            gwt({
              id: "PW-A11Y-001",
              title:
                "every kind of page passes the accessibility check, in each language, width and colour scheme",
              given:
                "a page of one of the site's kinds, in a language, at phone or desktop width, in light or dark mode",
              when: ["it is opened", "everything it draws with a script is in place"],
              then: "an accessibility check against the WCAG 2.2 AA rules finds no serious or critical problem",
            }),
            async ({ page }) => {
              // Not "networkidle", which waits a fixed half second with no traffic after every load. The
              // page scripts start before the load event and show a busy block while they fetch and draw,
              // so once no busy block is visible the script-drawn parts (charts, the calculator's result)
              // are in place.
              await page.goto(path);
              await expect(page.locator('[aria-busy="true"]:visible')).toHaveCount(0);
              await check(page, path);
            },
          );
        }

        test(
          `/${lang}/${M5} with a status shown alone and a source's definition open`,
          gwt({
            id: "PW-A11Y-003",
            title:
              "the consistency topic passes the accessibility check with a status filter applied and a source's definition open",
            given:
              "the consistency topic's Checks page and a question's page, in a language, at phone or desktop width, in light or dark mode",
            when: [
              "each status button on the Checks page is pressed in turn",
              "on the rent-paid question, a source's definition is opened",
            ],
            then: "an accessibility check against the WCAG 2.2 AA rules finds no serious or critical problem in each state",
          }),
          async ({ page }) => {
            await page.goto(`/${lang}/${M5}checks/`);
            const buttons = page.locator(
              '[data-m5="filter"] button[data-filter]:not([data-filter="all"])',
            );
            for (const button of await buttons.all()) {
              await button.click();
              await expect(button).toHaveAttribute("aria-pressed", "true");
              await check(
                page,
                `/${lang}/${M5}checks/ (${await button.getAttribute("data-filter")})`,
              );
            }
            await page.goto(`/${lang}/${M5}same-question/rent-paid/`);
            const term = page
              .locator('[data-m5="question"] th[data-m5-source] button.term')
              .first();
            await term.focus();
            await page.keyboard.press("Enter"); // opens the definition on every device (a mouse click follows the link)
            await expect(
              page.locator('[data-m5="question"] th[data-m5-source] .term-popover').first(),
            ).toBeVisible();
            await check(page, `/${lang}/${M5}same-question/rent-paid/ (a definition open)`);
          },
        );

        test(
          `/${lang}/ with each menu open`,
          gwt({
            id: "PW-A11Y-002",
            title: "the home page passes the accessibility check with each header menu open",
            given: "the home page, in a language, at phone or desktop width, in light or dark mode",
            when: "each menu for that width is opened in turn (the header's quick lists on a wide screen, the whole menu on a phone)",
            then: [
              "each menu opens",
              "an accessibility check against the WCAG 2.2 AA rules finds no serious or critical problem while it is open",
              "Escape closes it again",
            ],
          }),
          async ({ page }) => {
            await page.goto(`/${lang}/`); // the home page fetches nothing after it loads
            for (const id of MENUS[name]) {
              await page.locator(`button[popovertarget="${id}"]`).click();
              await expect(page.locator(`#${id}`)).toBeVisible();
              await check(page, `/${lang}/ (${id} open)`);
              await page.keyboard.press("Escape");
              await expect(page.locator(`#${id}`)).toBeHidden();
            }
          },
        );
      }
    });
  }
}
