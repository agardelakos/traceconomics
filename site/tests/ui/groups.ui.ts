// The Groups page's two tools. The finder: from a household, its net income, its home and its main
// income, the site's groups it belongs to, with links that carry the groups and never the income.
// The income panel: each fifth's income range for the household and unit the reader picks.
//
// Expected values come from the same exported limits file the page is built from (ours first,
// Eurostat's on the switch) and the site's own income functions (which have their own unit tests):
// here we check the page shows what they give.
import { readFileSync } from "node:fs";
import type { Locator, Page } from "@playwright/test";
import { amount, equivalentSize, FIFTHS, HOUSEHOLD_TYPES, placeIncome, ranges, type Unit } from "../../src/lib/income";
import { pct } from "../../src/lib/format";
import { expect, m1, num, t, test } from "./helpers";

const limits = JSON.parse(readFileSync(new URL("../../public/data/v1/gr/m1/latest/income-limits.json", import.meta.url), "utf-8"));
type Source = "ours" | "eurostat";
const TOP: Record<string, number> = limits.ours.top_cutoffs;
const PAGE = m1("en", "groups/");

const finder = (page: Page) => page.locator("#find");
const panel = (page: Page) => page.locator("#income");

/** A yearly income well inside a fifth (halfway between its limits), for a household of this size. */
function inside(fifth: "Q2" | "Q3" | "Q4", size: number) {
  const i = FIFTHS.indexOf(fifth);
  return Math.round(((TOP[FIFTHS[i - 1]] + TOP[fifth]) / 2) * size);
}

async function setHousehold(box: Locator, older: number, children: number) {
  await box.getByLabel(t("en", "income.older")).fill(String(older));
  await box.getByLabel(t("en", "income.children")).fill(String(children));
}

test.describe("the group finder", () => {
  test("shows the form (not the no-script note) and asks for an income first", async ({ page }) => {
    await page.goto(PAGE);
    const f = finder(page);
    await expect(f.getByText(t("en", "find.noscript"))).toBeHidden();
    await expect(f.getByText(t("en", "find.empty"))).toBeVisible();
    await expect(f.getByRole("link", { name: new RegExp(t("en", "find.compare")) })).toBeHidden();
  });

  test("places a yearly income in its fifth, and says how big the household counts", async ({ page }) => {
    await page.goto(PAGE);
    const f = finder(page);
    await setHousehold(f, 2, 1);
    const size = equivalentSize(2, 1);
    await expect(f.locator('[data-find="size"]')).toHaveText(t("en", "income.size", { size: num("en", size) }));
    const yearly = inside("Q3", size);
    const place = placeIncome(TOP, size, yearly);
    expect(place.fifth).toBe("Q3");
    await f.getByLabel(t("en", "find.income")).fill(String(yearly));
    await expect(f.locator('[data-find="income-value"]')).toHaveText(t("en", `group.${place.fifth}`));
    await expect(f.getByText(t("en", "find.empty"))).toBeHidden();
    await expect(f.locator('[data-find="near"]')).toBeHidden();
  });

  test("a monthly amount counts as a twelfth of the year", async ({ page }) => {
    await page.goto(PAGE);
    const f = finder(page);
    const yearly = inside("Q4", 1);
    await f.getByLabel(t("en", "find.income")).fill(String(Math.round(yearly / 12)));
    await f.getByLabel(t("en", "find.per.month")).check();
    await expect(f.locator('[data-find="income-value"]')).toHaveText(t("en", `group.${placeIncome(TOP, 1, yearly).fifth}`));
  });

  test("an income just past a limit says it could be either group", async ({ page }) => {
    await page.goto(PAGE);
    const f = finder(page);
    const yearly = Math.round(TOP.Q2 * 1.01);
    const place = placeIncome(TOP, 1, yearly);
    expect(place.neighbour).toBeTruthy();
    await f.getByLabel(t("en", "find.income")).fill(String(yearly));
    await expect(f.locator('[data-find="near"]')).toHaveText(t("en", "find.near", { group: t("en", `group.in.${place.neighbour}`) }));
  });

  test("home and main income add their groups; the links carry the groups, never the income", async ({ page }) => {
    await page.goto(PAGE);
    const f = finder(page);
    const yearly = inside("Q2", 1);
    await f.getByLabel(t("en", "find.income")).fill(String(yearly));
    await f.getByLabel(t("en", "find.home.renter")).check();
    await f.getByLabel(t("en", "find.yes"), { exact: true }).check();
    await expect(f.locator('[data-find="home-value"]')).toHaveText(t("en", "group.tenure/renter"));
    await expect(f.locator('[data-find="pension-value"]')).toHaveText(t("en", "group.pensioners/pensioners"));

    const starts = f.locator('[data-find="starts"] a');
    await expect(starts).toHaveCount(3);
    const froms = await starts.evaluateAll((as) => as.map((a) => new URL((a as HTMLAnchorElement).href).searchParams.get("from")));
    expect(froms).toEqual(["B/Q2", "tenure/renter", "pensioners/pensioners"]);
    for (const a of await starts.all()) await expect(a).toHaveAttribute("href", new RegExp(`^${m1("en", "calculator/")}\\?`));

    const compare = f.getByRole("link", { name: new RegExp(t("en", "find.compare")) });
    const href = (await compare.getAttribute("href"))!;
    expect(new URL(href, page.url()).searchParams.get("groups")).toBe("Q2,tenure/renter,pensioners/pensioners");
    for (const h of [href, ...(await starts.evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).href)))]) {
      expect(h).not.toContain(String(yearly));
    }
  });

  test("without an income, only the home and main-income groups", async ({ page }) => {
    await page.goto(PAGE);
    const f = finder(page);
    await f.getByLabel(t("en", "find.home.owner")).check();
    await f.getByLabel(t("en", "find.no"), { exact: true }).check();
    await expect(f.locator('[data-find="income-row"]')).toBeHidden();
    await expect(f.locator('[data-find="starts"] a')).toHaveCount(2);
  });

  test("out-of-range household numbers are kept within bounds for the sums", async ({ page }) => {
    await page.goto(PAGE);
    const f = finder(page);
    await setHousehold(f, 0, -3);        // below the minimum: counts as one adult, no children
    await expect(f.locator('[data-find="size"]')).toHaveText(t("en", "income.size", { size: num("en", equivalentSize(1, 0)) }));
  });

  test("the start buttons open the calculator from that group", async ({ page, coverage }) => {
    await page.goto(PAGE);
    const f = finder(page);
    await f.getByLabel(t("en", "find.home.renter")).check();
    await coverage.flush();
    await f.locator('[data-find="starts"] a').first().click();
    await expect(page).toHaveURL(/\/calculator\/\?from=tenure%2Frenter$/);
  });
});

test.describe("the income panel", () => {
  /** The rows as the page should show them. */
  function expected(size: number, unit: Unit, source: Source = "ours") {
    const cut: Record<string, number> = limits[source][unit === "pps" ? "top_cutoffs_pps" : "top_cutoffs"];
    return ranges(cut, size).map((r) => (["year", "month"] as const).map((per) => {
      const d = per === "year" ? 1 : 12;
      const a = (v: number) => amount(unit, v / d);
      if (r.from === null) return t("en", `income.${per}.upto`, { amount: a(r.to!) });
      if (r.to === null) return t("en", `income.${per}.over`, { amount: a(r.from) });
      return t("en", `income.${per}.between`, { from: a(r.from), to: a(r.to) });
    }));
  }

  async function expectRows(page: Page, size: number, unit: Unit, source: Source = "ours") {
    const rows = expected(size, unit, source);
    for (const [i, q] of FIFTHS.entries()) {
      await expect(panel(page).locator(`[data-income-year="${q}"]`)).toHaveText(rows[i][0]);
      await expect(panel(page).locator(`[data-income-month="${q}"]`)).toHaveText(rows[i][1]);
    }
  }

  test("each household type shows its ranges and its size", async ({ page }) => {
    await page.goto(PAGE);
    for (const h of HOUSEHOLD_TYPES) {
      await panel(page).getByLabel(t("en", `income.hh.${h.key}`), { exact: true }).check();
      const size = equivalentSize(h.older, h.children);
      await expect(panel(page).locator('[data-income-role="size"]')).toHaveText(t("en", "income.size", { size: num("en", size) }));
      await expectRows(page, size, "eur");
    }
  });

  test("Other opens the boxes for any household", async ({ page }) => {
    await page.goto(PAGE);
    const box = panel(page).locator('[data-income-role="other"]');
    await expect(box).toBeHidden();
    await panel(page).getByLabel(t("en", "income.hh.other"), { exact: true }).check();
    await expect(box).toBeVisible();
    await setHousehold(box, 4, 2);
    await expectRows(page, equivalentSize(4, 2), "eur");
  });

  test("purchasing power standards replace euros, or are greyed with the reason", async ({ page }) => {
    await page.goto(PAGE);
    const pps = panel(page).getByLabel(t("en", "income.unit.pps"));
    if (limits.ours.top_cutoffs_pps === null) {
      // No conversion for our year's incomes yet.
      await expect(pps).toBeDisabled();
      await expect(panel(page).locator('[data-income-role="pps-none"]')).toBeVisible();
    } else {
      await pps.check();
      await expectRows(page, 1, "pps");
    }
  });

  test("Eurostat's limits are one click away, in both units", async ({ page }) => {
    await page.goto(PAGE);
    await expect(panel(page).getByLabel(t("en", "income.source.ours"))).toBeChecked();
    await panel(page).getByLabel(t("en", "income.source.eurostat")).check();
    await expectRows(page, 1, "eur", "eurostat");
    await panel(page).getByLabel(t("en", "income.unit.pps")).check();
    await expectRows(page, 1, "pps", "eurostat");
  });

  test("our limits say how they are made, and how far Eurostat's are from them", async ({ page }) => {
    const ours = limits.ours, eu = limits.eurostat;
    await page.goto(PAGE);
    const ses = Object.values(ours.se as Record<string, number | null>).filter((v): v is number => v !== null);
    await expect(panel(page).locator('[data-income-role="ours-note"]')).toHaveText(t("en", "income.source.ours_note", {
      survey: ours.survey_year, income: ours.income_year, se_from: amount("eur", Math.min(...ses)), se_to: amount("eur", Math.max(...ses)),
    }));
    if (eu.income_year === ours.income_year) {
      const a = eu.top_cutoffs.Q1, b = ours.top_cutoffs.Q1;
      const diff = t("en", a <= b ? "income.compare.lower" : "income.compare.higher", { pct: pct("en", (Math.abs(a - b) / b) * 100) });
      await expect(panel(page).locator('[data-income-role="compare"]')).toHaveText(t("en", "income.source.compare", {
        income: ours.income_year, eurostat: amount("eur", a), ours: amount("eur", b), diff,
      }));
    }
    await expect(finder(page)).toContainText(t("en", "find.limits", { year: ours.survey_year }));
  });
});
