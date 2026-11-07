// Without scripts. The navigation and the term explanations are the browser's own popovers, so they
// still open; controls that need a script stay hidden rather than sit there broken; the Groups page
// says its finder needs one and still shows the income table, for one adult, in euros; Explore and
// the calculator say they need one and link to the data files.
import { readFileSync } from "node:fs";
import { amount, FIFTHS, ranges } from "../../src/lib/income";
import { expect, gwt, m1, t, test } from "./helpers";

test.use({ javaScriptEnabled: false });

test("the theme setting, which needs a script, stays hidden", gwt({
  id: "PW-NOJS-001",
  given: "a browser with scripts turned off",
  when: "the home page opens",
  then: "the theme setting's button is not shown",
}), async ({ page }) => {
  await page.goto("/en/");
  await expect(page.getByRole("button", { name: t("en", "settings.label") })).toBeHidden();
});

test("the header's quick lists still open", gwt({
  id: "PW-NOJS-002",
  given: ["a browser with scripts turned off", "the home page"],
  when: "the arrow beside Topics in the header is pressed",
  then: "the quick list of topics opens",
}), async ({ page }) => {
  await page.goto("/en/");
  await page.getByRole("button", { name: t("en", "nav.quick", { name: t("en", "nav.topics") }) }).click();
  await expect(page.locator("#topic-menu")).toBeVisible();
});

test("a term's explanation still opens, with its link", gwt({
  id: "PW-NOJS-003",
  given: ["a browser with scripts turned off", "the method page"],
  when: "the first explained term is pressed",
  then: ["its explanation opens", "the explanation shows its link"],
}), async ({ page }) => {
  await page.goto(m1("en", "method/"));
  const button = page.locator(".term-wrap button.term").first();
  const pop = page.locator(`[id="${await button.getAttribute("popovertarget")}"]`);
  await button.click();
  await expect(pop).toBeVisible();
  await expect(pop.getByRole("link")).toBeVisible();
});

test("the Groups page says the finder needs a script, and shows the income table", gwt({
  id: "PW-NOJS-004",
  given: "a browser with scripts turned off",
  when: "the Groups page opens",
  then: ["it says the group finder needs a script, and the finder's form is not shown",
    "the income table shows the poorest fifth's yearly limit from our own limits, for one adult, in euros",
    "the table has one row per fifth"],
}), async ({ page }) => {
  // The page is built showing our limits, for one adult, in euros.
  const cut = JSON.parse(readFileSync(new URL("../../public/data/v1/gr/m1/latest/income-limits.json", import.meta.url), "utf-8")).ours.top_cutoffs;
  await page.goto(m1("en", "groups/"));
  await expect(page.getByText(t("en", "find.noscript"))).toBeVisible();
  await expect(page.locator('#find [data-find="form"]')).toBeHidden();
  const first = ranges(cut, 1)[0];
  await expect(page.locator('#income [data-income-year="Q1"]')).toHaveText(t("en", "income.year.upto", { amount: amount("eur", first.to!) }));
  await expect(page.locator("#income tbody tr")).toHaveCount(FIFTHS.length);
});

// Explore and the calculator can't work without a script: each says so and links to the data
// files, instead of a loading message that never ends.
for (const [page_, key, box] of [["explore/", "explore.noscript", "#explore"], ["calculator/", "calc.noscript", "#calculator"]] as const) {
  test(`${page_.replace("/", "")} says it needs a script and links to the data files`, gwt({
    id: "PW-NOJS-005",
    title: "a page that needs a script says so and links to the data files",
    given: "a browser with scripts turned off",
    when: "a page that draws with a script (Explore or the calculator) opens",
    then: ["it shows a line saying it needs a script, with a link to the data files page for Greece", "no loading message is shown",
      "on Explore, the chart's controls are not shown"],
  }), async ({ page }) => {
    await page.goto(m1("en", page_));
    const line = page.locator(`${box} [data-role="noscript"]`);
    await expect(line).toBeVisible();
    await expect(line).toContainText(t("en", key));
    await expect(line.getByRole("link", { name: new RegExp(t("en", "noscript.data")) })).toHaveAttribute("href", "/en/data/gr/");
    await expect(page.locator(`${box} [data-role="loading"]`)).toBeHidden();
    if (box === "#explore") await expect(page.locator(`${box} [data-role="view-time"]`)).toBeHidden();
  });
}
