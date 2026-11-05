// The calculator: start from a group, change where the money goes (as shares or in euros a month),
// read your annual inflation against the group's. Left untouched it must show the published series'
// own latest rate (it reproduces the official numbers); changed, it must show what the engine gives
// for those shares (the engine has its own unit and parity tests: here we check the page's wiring).
import type { APIRequestContext, Page } from "@playwright/test";
import { annualRate, chain, divisionShares, presetWeights, published, type CalculatorData, type Shares } from "../../src/lib/engine/calculator";
import { roundHalfEven } from "../../src/lib/engine/round";
import { eur } from "../../src/lib/income";
import { expect, json, LANGS, m1, month, num, t, test, type Lang } from "./helpers";

const DATA = "/data/v1/gr/m1/latest";
const root = (page: Page) => page.locator("#calculator");
const role = (page: Page, r: string) => root(page).locator(`[data-role="${r}"]`);

/** The published series' latest annual rate for a group, and its month. */
async function publishedRate(request: APIRequestContext, group: string) {
  const s = await json(request, `${DATA}/settings.json`);
  const file = await json(request, `${DATA}/series/${s.default}.json`);
  const values: (number | null)[] = file.groups[group].rch_a;
  let i = values.length - 1;
  while (values[i] === null) i--;
  const [y, m] = file.start.split("-").map(Number);
  const months = y * 12 + (m - 1) + i;
  return { value: values[i]!, period: `${Math.floor(months / 12)}-${String((months % 12) + 1).padStart(2, "0")}` };
}

/** What the engine gives for these shares (as the page computes it). */
function engineRate(data: CalculatorData, preset: string, shares: Shares | undefined, period: string) {
  return roundHalfEven(annualRate(published(chain(data, preset, shares)), period)!, 1);
}
function presetShares(data: CalculatorData, preset: string): Shares {
  const w = presetWeights(data, preset);
  return divisionShares(w.get(Math.max(...w.keys()))!);
}
const config = async (page: Page) => JSON.parse((await root(page).getAttribute("data-config"))!);
const pct = (lang: Lang, v: number) => `${num(lang, v)}%`;

for (const lang of LANGS) {
  test(`${lang}: untouched, it shows the published series' latest rate`, async ({ page, request }) => {
    const q1 = await publishedRate(request, "B/Q1");
    const all = await publishedRate(request, "all/all");
    await page.goto(m1(lang, "calculator/"));
    await expect(role(page, "result")).toBeVisible();
    await expect(role(page, "loading")).toBeHidden();
    await expect(role(page, "noscript")).toBeHidden();
    await expect(role(page, "yours")).toHaveText(pct(lang, q1.value));
    await expect(role(page, "yours-label")).toHaveText(t(lang, "calc.yours", { month: month(lang, q1.period) }));
    await expect(role(page, "preset-rate")).toHaveText(pct(lang, q1.value));
    await expect(role(page, "all-rate")).toHaveText(pct(lang, all.value));
    const name = (await config(page)).presets.find((p: any) => p.key === "B/Q1").name;
    await expect(role(page, "same")).toHaveText(t(lang, "calc.same", { preset: name }));
    await expect(role(page, "diff")).toBeHidden();
    await expect(role(page, "reset")).toBeHidden();
    await expect(role(page, "chart").locator("svg").first()).toBeVisible();
  });
}

test("another starting group shows its own rate and goes in the address", async ({ page, request }) => {
  const renter = await publishedRate(request, "tenure/renter");
  await page.goto(m1("en", "calculator/"));
  await role(page, "preset").selectOption("tenure/renter");
  await expect(role(page, "yours")).toHaveText(pct("en", renter.value));
  // The address is updated after the result is drawn: wait for it rather than read it once.
  await expect.poll(() => new URL(page.url()).searchParams.get("from")).toBe("tenure/renter");
});

test("the group finder's link starts from its group; an unknown one from the default", async ({ page, request }) => {
  const pens = await publishedRate(request, "pensioners/pensioners");
  await page.goto(`${m1("en", "calculator/")}?from=pensioners/pensioners`);
  await expect(role(page, "preset")).toHaveValue("pensioners/pensioners");
  await expect(role(page, "yours")).toHaveText(pct("en", pens.value));
  await page.goto(`${m1("en", "calculator/")}?from=nope`);
  await expect(role(page, "preset")).toHaveValue("B/Q1");
});

test("moving a slider gives the engine's rate, adjusts the others, and Reset undoes it", async ({ page, request }) => {
  const data: CalculatorData = await json(request, `${DATA}/calculator.json`);
  const { period } = await publishedRate(request, "B/Q1");
  await page.goto(m1("en", "calculator/"));
  await expect(role(page, "result")).toBeVisible();
  const cfg = await config(page);
  const codes = Object.keys(cfg.divisions).sort();
  const [d, other] = [codes.includes("04") ? "04" : codes[0], codes.find((c) => c !== "04")!];

  // The page's rule: the moved category takes the new share, the others scale to keep 100%.
  const before = presetShares(data, "B/Q1");
  const v = 0.4;
  const rest = codes.filter((c) => c !== d).reduce((a, c) => a + (before[c] ?? 0), 0);
  const shares: Shares = Object.fromEntries(codes.map((c) => [c, c === d ? v : (before[c] ?? 0) * ((1 - v) / rest)]));
  const yours = engineRate(data, "B/Q1", shares, period);
  const theirs = engineRate(data, "B/Q1", undefined, period);

  await root(page).getByLabel(cfg.divisions[d], { exact: true }).fill("40");
  await expect(role(page, "yours")).toHaveText(pct("en", yours));
  const gap = roundHalfEven(yours - theirs, 1);
  const name = cfg.presets.find((p: any) => p.key === "B/Q1").name;
  await expect(role(page, "diff")).toHaveText(t("en", gap >= 0 ? "calc.diff_up" : "calc.diff_down", { points: num("en", Math.abs(gap)), preset: name }));
  await expect(role(page, "same")).toBeHidden();
  await expect(role(page, "rescaled")).toBeVisible();
  const notes = role(page, "sliders").locator(".slider-row");
  await expect(notes.nth(codes.indexOf(d)).locator(".small")).toHaveText(t("en", "calc.changed", { value: pct("en", (before[d] ?? 0) * 100) }));
  if ((before[other] ?? 0) > 0) {
    await expect(notes.nth(codes.indexOf(other)).locator(".small")).toHaveText(t("en", "calc.adjusted", { value: pct("en", before[other] * 100) }));
  }
  await expect(role(page, "chart")).toHaveAttribute("aria-label", new RegExp(t("en", "calc.title")));

  const reset = role(page, "reset");
  await expect(reset).toHaveText(t("en", "calc.reset", { preset: name }));
  await reset.click();
  await expect(role(page, "same")).toBeVisible();
  await expect(role(page, "rescaled")).toBeHidden();
  await expect(role(page, "yours")).toHaveText(pct("en", theirs));
});

test("in euros a month: shares, a total, the engine's rate; a bad amount is flagged; then back to shares", async ({ page, request }) => {
  const data: CalculatorData = await json(request, `${DATA}/calculator.json`);
  const { period } = await publishedRate(request, "B/Q1");
  await page.goto(m1("en", "calculator/"));
  await expect(role(page, "result")).toBeVisible();
  const cfg = await config(page);
  const codes = Object.keys(cfg.divisions).sort();
  const [a, b] = codes;
  const input = (code: string) => root(page).getByLabel(t("en", "calc.euros.input", { category: cfg.divisions[code] }));

  await root(page).getByRole("button", { name: t("en", "calc.mode.euros") }).click();
  await expect(role(page, "pane-euros")).toBeVisible();
  await expect(role(page, "euros-empty")).toBeVisible();
  await input(a).fill("300");
  await input(b).fill("700");
  await expect(role(page, "euros-total")).toHaveText(t("en", "calc.euros.total", { amount: eur(1000, 0) }));
  await expect(root(page).locator(`#eur-${a}-share`)).toHaveText(t("en", "calc.euros.share", { share: pct("en", 30) }));
  await expect(role(page, "euros-empty")).toBeHidden();
  const shares: Shares = Object.fromEntries(codes.map((c) => [c, c === a ? 0.3 : c === b ? 0.7 : 0]));
  await expect(role(page, "yours")).toHaveText(pct("en", engineRate(data, "B/Q1", shares, period)));

  await input(codes[2]).fill("abc");
  await expect(root(page).locator(`#eur-${codes[2]}-share`)).toHaveText(t("en", "calc.euros.invalid"));
  await expect(input(codes[2])).toHaveAttribute("aria-invalid", "");
  await input(codes[2]).fill("");

  // A new starting group keeps the reader's own amounts.
  await role(page, "preset").selectOption("tenure/owner");
  await expect(input(a)).toHaveValue("300");
  await expect(role(page, "yours")).toHaveText(pct("en", engineRate(data, "tenure/owner", shares, period)));

  // Back to shares: the sliders start from the euros' shares.
  await root(page).getByRole("button", { name: t("en", "calc.mode.shares") }).click();
  await expect(role(page, "sliders").locator(".slider-row").nth(0).locator(".num")).toHaveText(pct("en", 30));
  await expect(root(page).getByLabel(cfg.divisions[a], { exact: true })).toHaveValue(/^30(\.0+)?$/);

  await root(page).getByRole("button", { name: t("en", "calc.mode.euros") }).click();
  await role(page, "reset").click();                                   // "Clear the amounts"
  await expect(input(a)).toHaveValue("");
  await expect(role(page, "euros-empty")).toBeVisible();
});

test.describe("when the calculator's file can't be loaded", () => {
  // The browser itself logs the refused request; that's the point of this test.
  test.use({ allowErrors: [/Failed to load resource/] });

  test("it says so instead of showing a number", async ({ page }) => {
    await page.route("**/calculator.json", (route) => route.fulfill({ status: 503, body: "" }));
    await page.goto(m1("en", "calculator/"));
    await expect(role(page, "loading")).toHaveText(t("en", "chart.failed"));
    await expect(role(page, "result")).toBeHidden();
  });
});
