// Getting around: the header's quick lists (Topics, Countries), the highlighted current section,
// the phone menu, the breadcrumb, the language switch and the root address's choice of language.
// The quick lists and the phone menu are popovers, so they also work without scripts.
import { expect, gwt, LANGS, m1, OFFERED, t, test } from "./helpers";

const quick = (name: string) => t("en", "nav.quick", { name: t("en", name) });

test(
  "the Topics quick list opens, ticks the current topic, and closes with Escape",
  gwt({
    id: "PW-NAV-001",
    given: "the inflation-by-group page for Greece, with the Topics quick list closed",
    when: ["the arrow beside Topics in the header is pressed", "Escape is pressed"],
    then: [
      "the quick list opens, with inflation by group marked as the current topic",
      "planned topics are shown as coming soon",
      "Escape closes the list",
    ],
  }),
  async ({ page }) => {
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
  },
);

test(
  "the Countries quick list ticks the current country and links to the same page there",
  gwt({
    id: "PW-NAV-002",
    given: "Explore for Greece",
    when: "the arrow beside Countries in the header is pressed",
    then: [
      "Greece is marked as the current country, and its link goes to the same page (Explore) for Greece",
      "a link to all countries goes to the countries page",
    ],
  }),
  async ({ page }) => {
    await page.goto(m1("en", "explore/"));
    await page.getByRole("button", { name: quick("nav.countries") }).click();
    const list = page.locator("#country-menu");
    const greece = list.getByRole("link", { name: t("en", "country.gr") });
    await expect(greece).toHaveAttribute("aria-current", "true");
    await expect(greece).toHaveAttribute("href", /\/en\/gr\/inflation-by-group\/explore\/?$/);
    await expect(
      list.getByRole("link", { name: new RegExp(t("en", "topic.all_countries")) }),
    ).toHaveAttribute("href", /\/en\/countries\/?$/);
  },
);

test(
  "picking a quick-list entry goes to its page",
  gwt({
    id: "PW-NAV-011",
    given: "the About page",
    when: "the Countries quick list is opened and Greece is picked",
    then: "the browser goes to the Greece page",
  }),
  async ({ page, coverage }) => {
    await page.goto("/en/about/");
    await page.getByRole("button", { name: quick("nav.countries") }).click();
    await coverage.flush();
    await page
      .locator("#country-menu")
      .getByRole("link", { name: t("en", "country.gr") })
      .click();
    await expect(page).toHaveURL(/\/en\/gr\/$/);
  },
);

test(
  "on a desktop the navigation shows as a row, with no menu button",
  gwt({
    id: "PW-NAV-012",
    given: "a desktop-sized window",
    when: "the home page opens",
    then: [
      "the navigation and the theme setting's button are shown",
      "the phone's menu button is not",
    ],
  }),
  async ({ page }) => {
    await page.goto("/en/");
    await expect(page.getByRole("navigation", { name: t("en", "nav.label") })).toBeVisible();
    await expect(page.getByRole("button", { name: t("en", "settings.label") })).toBeVisible();
    await expect(page.getByRole("button", { name: t("en", "nav.menu") })).toBeHidden();
  },
);

test(
  "the skip link takes the keyboard to the main content",
  gwt({
    id: "PW-NAV-013",
    given: "the About page",
    when: ["Tab is pressed once", "Enter is pressed"],
    then: [
      "the skip link has the focus and shows",
      "the address moves to the main content (#content)",
    ],
  }),
  async ({ page }) => {
    await page.goto("/en/about/");
    await page.keyboard.press("Tab");
    const skip = page.locator("a.skip-link");
    await expect(skip).toBeFocused();
    await expect(skip).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#content$/);
  },
);

test(
  "opening one quick list closes the other",
  gwt({
    id: "PW-NAV-003",
    given: "the home page, with the Topics quick list open",
    when: "the Countries quick list is opened",
    then: ["the Countries list is shown", "the Topics list is closed"],
  }),
  async ({ page }) => {
    await page.goto("/en/");
    await page.getByRole("button", { name: quick("nav.topics") }).click();
    await page.getByRole("button", { name: quick("nav.countries") }).click();
    await expect(page.locator("#country-menu")).toBeVisible();
    await expect(page.locator("#topic-menu")).toBeHidden();
  },
);

for (const [path, key] of [
  ["/en/glossary/", "nav.glossary"],
  ["/en/topics/", "nav.topics"],
] as const) {
  test(
    `${t("en", key)} is marked as the current page on ${path}`,
    gwt({
      id: "PW-NAV-004",
      title: "on a section's own page, the header marks its link as the current page",
      given: "a page that is a section of the navigation (Glossary, Topics)",
      when: "it opens",
      then: 'that section\'s link in the navigation is marked as the current page (aria-current="page")',
    }),
    async ({ page }) => {
      await page.goto(path);
      const nav = page.getByRole("navigation", { name: t("en", "nav.label") });
      await expect(nav.getByRole("link", { name: t("en", key), exact: true })).toHaveAttribute(
        "aria-current",
        "page",
      );
    },
  );
}

test(
  "on a page inside a section, the header marks the section as current",
  gwt({
    id: "PW-NAV-010",
    given: "a country's page, which is inside Countries",
    when: "it opens",
    then: 'the Countries link in the navigation is marked as the current section (aria-current="true"), not as the current page',
  }),
  async ({ page }) => {
    await page.goto(m1("en"));
    const nav = page.getByRole("navigation", { name: t("en", "nav.label") });
    await expect(
      nav.getByRole("link", { name: t("en", "nav.countries"), exact: true }),
    ).toHaveAttribute("aria-current", "true");
  },
);

test(
  "the breadcrumb leads back home",
  gwt({
    id: "PW-NAV-005",
    given: "a glossary term's page",
    when: "the breadcrumb's Home link is pressed",
    then: ["the breadcrumb is shown", "the browser goes to the English home page"],
  }),
  async ({ page, coverage }) => {
    await page.goto("/en/glossary/imputed-rent/");
    const crumbs = page.getByRole("navigation", { name: t("en", "breadcrumb") });
    await expect(crumbs).toBeVisible();
    await coverage.flush();
    await crumbs.getByRole("link", { name: t("en", "nav.home") }).click();
    await expect(page).toHaveURL(/\/en\/$/);
  },
);

test(
  "the language switch links offered languages to the same page and greys the others",
  gwt({
    id: "PW-NAV-006",
    given: "the About page in English",
    when: "the language switch is read",
    then: [
      "each offered language links to the About page in that language",
      "each language not yet offered is greyed out as unavailable, with no link",
      "English is marked as the current language",
    ],
  }),
  async ({ page }) => {
    await page.goto("/en/about/");
    const sw = page.getByRole("group", { name: t("en", "lang.switch") });
    for (const lang of LANGS) {
      const code = lang.toUpperCase().replace("EL", "ΕΛ");
      if (OFFERED.includes(lang)) {
        await expect(sw.getByRole("link", { name: code })).toHaveAttribute(
          "href",
          new RegExp(`/${lang}/about/?$`),
        );
      } else {
        await expect(sw.getByText(code)).toHaveAttribute("aria-disabled", "true");
        await expect(sw.getByRole("link", { name: code })).toHaveCount(0);
      }
    }
    await expect(sw.getByRole("link", { name: "EN" })).toHaveAttribute("aria-current", "true");
  },
);

// The root address picks the first of the browser's languages that the site offers, else English.
for (const locale of ["el-GR", "en-US", "de-DE"]) {
  test.describe(`a browser in ${locale}`, () => {
    test.use({ locale });
    test(
      "is sent from the root to the right language",
      gwt({
        id: "PW-NAV-007",
        title: "the root address sends each browser to its language",
        given: "a browser set to a language",
        when: "the site's root address is opened",
        then: "the visitor is sent to the home page in the browser's language if the site offers it, else in English",
      }),
      async ({ page }) => {
        const wanted = locale.split("-")[0] as (typeof LANGS)[number];
        const expected = OFFERED.includes(wanted) ? wanted : "en";
        await page.goto("/");
        await expect(page).toHaveURL(new RegExp(`/${expected}/$`));
      },
    );
  });
}

test.describe("without scripts, the root page", () => {
  test.use({ javaScriptEnabled: false });
  test(
    "offers a link to each offered language",
    gwt({
      id: "PW-NAV-008",
      given: "a browser with scripts turned off",
      when: "the site's root address is opened",
      then: "the page shows a link to the home page of each offered language",
    }),
    async ({ page }) => {
      await page.goto("/");
      for (const lang of OFFERED)
        await expect(page.locator(`main a[href="/${lang}/"]`)).toBeVisible();
    },
  );
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

  test(
    "the menu button opens the navigation, and its links work",
    gwt({
      id: "PW-NAV-009",
      given: "the home page on a phone, with the navigation hidden",
      when: ["the menu button is pressed", "the Glossary link in it is pressed"],
      then: [
        "the navigation is shown",
        "the browser goes to the glossary",
        "the navigation is hidden again on the new page",
      ],
    }),
    async ({ page, coverage }) => {
      await page.goto("/en/");
      const nav = page.getByRole("navigation", { name: t("en", "nav.label") });
      await expect(nav).toBeHidden();
      await page.getByRole("button", { name: t("en", "nav.menu") }).click();
      await expect(nav).toBeVisible();
      await coverage.flush();
      await nav.getByRole("link", { name: t("en", "nav.glossary"), exact: true }).click();
      await expect(page).toHaveURL(/\/en\/glossary\/$/);
      await expect(nav).toBeHidden();
    },
  );
});

test(
  "on a phone, each row of the topic bar opens scrolled to its current item",
  gwt({
    id: "PW-NAV-014",
    given: [
      "a phone-sized screen",
      "Greece's page of the consistency topic, whose row of topics is wider than the screen with the current topic last",
    ],
    when: "it is opened",
    then: "in every row of the bar wider than the screen, the current item is wholly inside the row's visible part",
  }),
  async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/en/gr/official-figures-consistency/");
    const rows = page.locator(".topic-bar nav ul");
    let wide = 0;
    for (const row of await rows.all()) {
      const box = await row.evaluate((el) => ({
        scroll: el.scrollWidth,
        client: el.clientWidth,
        left: el.getBoundingClientRect().left,
      }));
      if (box.scroll <= box.client) continue;
      wide += 1;
      const item = await row.locator("[aria-current]").boundingBox();
      expect(item!.x).toBeGreaterThanOrEqual(box.left - 1);
      expect(item!.x + item!.width).toBeLessThanOrEqual(box.left + box.client + 1);
    }
    expect(wide).toBeGreaterThan(0);
  },
);

test(
  "on a method option's page, the bar's third row lists every option and marks the one being read",
  gwt({
    id: "PW-NAV-015",
    given: "the method page, which lists every option, and one option's page",
    when: "the option's page is opened from the method page",
    then: [
      "the bar's third row lists the options in the method page's order, by their titles",
      "the option being read is plain text marked current; the others link to their pages",
      "the Method tab is marked as the current section",
    ],
  }),
  async ({ page, coverage }) => {
    await page.goto(m1("en", "method/"));
    const cards = page.locator('nav[aria-labelledby="options-h"] a.card');
    const titles = (await cards.locator(".title").allTextContents()).map((x) =>
      x.replace(/ →$/, ""),
    );
    const hrefs = await cards.evaluateAll((as) => as.map((a) => a.getAttribute("href")!));
    await coverage.flush();
    await cards.nth(1).click();
    await expect(page).toHaveURL(new RegExp(`${hrefs[1]}$`));
    const strip = page.locator("nav[data-strip]");
    await expect(strip.locator("li")).toHaveText(titles);
    await expect(strip.locator('[aria-current="page"]')).toHaveText(titles[1]);
    for (const [i, title] of titles.entries()) {
      if (i === 1) continue;
      await expect(strip.getByRole("link", { name: title, exact: true })).toHaveAttribute(
        "href",
        hrefs[i],
      );
    }
    await expect(
      page.locator(".topic-nav.sub a", { hasText: t("en", "nav.method") }),
    ).toHaveAttribute("aria-current", "true");
  },
);

test(
  "the Topics quick list names every live topic and leads to its page",
  gwt({
    id: "PW-NAV-016",
    given: "Greece's page of the consistency topic",
    when: "the arrow beside Topics in the header is pressed",
    then: [
      "the list links to both live topics, inflation by household and the consistency of official figures, each to its page",
      "the consistency topic is marked as the current one",
    ],
  }),
  async ({ page }) => {
    await page.goto("/en/gr/official-figures-consistency/");
    await page.getByRole("button", { name: quick("nav.topics") }).click();
    const list = page.locator("#topic-menu");
    await expect(list).toBeVisible();
    for (const slug of ["inflation-by-group", "official-figures-consistency"]) {
      await expect(list.getByRole("link", { name: t("en", `topic.${slug}`) })).toHaveAttribute(
        "href",
        `/en/${slug}/`,
      );
    }
    await expect(
      list.getByRole("link", { name: t("en", "topic.official-figures-consistency") }),
    ).toHaveAttribute("aria-current", "true");
  },
);
