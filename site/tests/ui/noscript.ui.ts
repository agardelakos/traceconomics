// Without scripts. The navigation and the term explanations are the browser's own popovers, so they
// still open; controls that need a script stay hidden rather than sit there broken; the Groups page
// says its finder needs one and still shows the income table, for one adult, in euros; Explore and
// the calculator say they need one and link to the data files.
import { readFileSync } from "node:fs";
import { amount, FIFTHS, ranges } from "../../src/lib/income";
import { expect, m1, t, test } from "./helpers";

test.use({ javaScriptEnabled: false });

test("the theme setting, which needs a script, stays hidden", async ({ page }) => {
  await page.goto("/en/");
  await expect(page.getByRole("button", { name: t("en", "settings.label") })).toBeHidden();
});

test("the header's quick lists still open", async ({ page }) => {
  await page.goto("/en/");
  await page.getByRole("button", { name: t("en", "nav.quick", { name: t("en", "nav.topics") }) }).click();
  await expect(page.locator("#topic-menu")).toBeVisible();
});

test("a term's explanation still opens, with its link", async ({ page }) => {
  await page.goto(m1("en", "method/"));
  const button = page.locator(".term-wrap button.term").first();
  const pop = page.locator(`[id="${await button.getAttribute("popovertarget")}"]`);
  await button.click();
  await expect(pop).toBeVisible();
  await expect(pop.getByRole("link")).toBeVisible();
});

test("the Groups page says the finder needs a script, and shows the income table", async ({ page }) => {
  const cut = JSON.parse(readFileSync(new URL("../../src/lib/income-cutoffs.json", import.meta.url), "utf-8")).eurostat.top_cutoffs;
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
  test(`${page_.replace("/", "")} says it needs a script and links to the data files`, async ({ page }) => {
    await page.goto(m1("en", page_));
    const line = page.locator(`${box} [data-role="noscript"]`);
    await expect(line).toBeVisible();
    await expect(line).toContainText(t("en", key));
    await expect(line.getByRole("link", { name: new RegExp(t("en", "noscript.data")) })).toHaveAttribute("href", "/en/data/gr/");
    await expect(page.locator(`${box} [data-role="loading"]`)).toBeHidden();
    if (box === "#explore") await expect(page.locator(`${box} [data-role="view-time"]`)).toBeHidden();
  });
}
