// Getting around: the header's quick lists (Topics, Countries), the highlighted current section,
// the phone menu, the breadcrumb, the language switch and the root address's choice of language.
// The quick lists and the phone menu are popovers, so they also work without scripts.
import { expect, LANGS, m1, OFFERED, t, test } from "./helpers";

const quick = (name: string) => t("en", "nav.quick", { name: t("en", name) });

test("the Topics quick list opens, ticks the current topic, and closes with Escape", async ({ page }) => {
  await page.goto(m1("en"));
  const list = page.locator("#topic-menu");
  await expect(list).toBeHidden();
  await page.getByRole("button", { name: quick("nav.topics") }).click();
  await expect(list).toBeVisible();
  const current = list.getByRole("link", { name: t("en", "topic.inflation-by-group") });
  await expect(current).toHaveAttribute("aria-current", "true");
  // Planned topics are shown as "soon", never as links.
  await expect(list.getByText(t("en", "soon")).first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(list).toBeHidden();
});

test("the Countries quick list ticks the current country and links to the same page there", async ({ page }) => {
  await page.goto(m1("en", "explore/"));
  await page.getByRole("button", { name: quick("nav.countries") }).click();
  const list = page.locator("#country-menu");
  const greece = list.getByRole("link", { name: t("en", "country.gr") });
  await expect(greece).toHaveAttribute("aria-current", "true");
  await expect(greece).toHaveAttribute("href", /\/en\/gr\/inflation-by-group\/explore\/?$/);
  await expect(list.getByRole("link", { name: new RegExp(t("en", "topic.all_countries")) })).toHaveAttribute("href", /\/en\/countries\/?$/);
});

test("opening one quick list closes the other", async ({ page }) => {
  await page.goto("/en/");
  await page.getByRole("button", { name: quick("nav.topics") }).click();
  await page.getByRole("button", { name: quick("nav.countries") }).click();
  await expect(page.locator("#country-menu")).toBeVisible();
  await expect(page.locator("#topic-menu")).toBeHidden();
});

for (const [path, key, value] of [
  ["/en/glossary/", "nav.glossary", "page"],
  ["/en/topics/", "nav.topics", "page"],
  [m1("en"), "nav.countries", "true"],   // a country's page is inside Countries
] as const) {
  test(`${t("en", key)} is marked current on ${path}`, async ({ page }) => {
    await page.goto(path);
    const nav = page.getByRole("navigation", { name: t("en", "nav.label") });
    await expect(nav.getByRole("link", { name: t("en", key), exact: true })).toHaveAttribute("aria-current", value);
  });
}

test("the breadcrumb leads back home", async ({ page, coverage }) => {
  await page.goto("/en/glossary/imputed-rent/");
  const crumbs = page.getByRole("navigation", { name: t("en", "breadcrumb") });
  await expect(crumbs).toBeVisible();
  await coverage.flush();
  await crumbs.getByRole("link", { name: t("en", "nav.home") }).click();
  await expect(page).toHaveURL(/\/en\/$/);
});

test("the language switch links offered languages to the same page and greys the others", async ({ page }) => {
  await page.goto("/en/about/");
  const sw = page.getByRole("group", { name: t("en", "lang.switch") });
  for (const lang of LANGS) {
    const code = lang.toUpperCase().replace("EL", "ΕΛ");
    if (OFFERED.includes(lang)) {
      await expect(sw.getByRole("link", { name: code })).toHaveAttribute("href", new RegExp(`/${lang}/about/?$`));
    } else {
      await expect(sw.getByText(code)).toHaveAttribute("aria-disabled", "true");
      await expect(sw.getByRole("link", { name: code })).toHaveCount(0);
    }
  }
  await expect(sw.getByRole("link", { name: "EN" })).toHaveAttribute("aria-current", "true");
});

// The root address picks the first of the browser's languages that the site offers, else English.
for (const locale of ["el-GR", "en-US", "de-DE"]) {
  test.describe(`a browser in ${locale}`, () => {
    test.use({ locale });
    test("is sent from the root to the right language", async ({ page }) => {
      const wanted = locale.split("-")[0] as (typeof LANGS)[number];
      const expected = OFFERED.includes(wanted) ? wanted : "en";
      await page.goto("/");
      await expect(page).toHaveURL(new RegExp(`/${expected}/$`));
    });
  });
}

test.describe("without scripts, the root page", () => {
  test.use({ javaScriptEnabled: false });
  test("offers a link to each offered language", async ({ page }) => {
    await page.goto("/");
    for (const lang of OFFERED) await expect(page.locator(`main a[href="/${lang}/"]`)).toBeVisible();
  });
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

  test("the menu button opens the navigation, and its links work", async ({ page, coverage }) => {
    await page.goto("/en/");
    const nav = page.getByRole("navigation", { name: t("en", "nav.label") });
    await expect(nav).toBeHidden();
    await page.getByRole("button", { name: t("en", "nav.menu") }).click();
    await expect(nav).toBeVisible();
    await coverage.flush();
    await nav.getByRole("link", { name: t("en", "nav.glossary"), exact: true }).click();
    await expect(page).toHaveURL(/\/en\/glossary\/$/);
    await expect(nav).toBeHidden();
  });
});
