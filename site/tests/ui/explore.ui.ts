// Explore: the groups, options, measure, gap and view live in the address, so a shared link opens
// the same view; the chart's summary, its data table, the breakdown, the files link and the
// citation follow the choice. Expected numbers come from the published files for that setting.
import type { APIRequestContext, Locator, Page } from "@playwright/test";
import { expect, json, LANGS, m1, month, num, t, test, type Lang } from "./helpers";

const DATA = "/data/v1/gr/m1/latest";
const DEFAULT_GROUPS = ["Q1", "Q5", "all/all"];
type Measure = "rch_a" | "rch_m" | "index";

const settings = (request: APIRequestContext) => json(request, `${DATA}/settings.json`);
const series = (request: APIRequestContext, slug: string) => json(request, `${DATA}/series/${slug}.json`);
const dataKey = (g: string) => (g.startsWith("Q") ? `B/${g}` : g);
const SLUG_KEYS = ["spending", "imputed_rent", "price_source", "weights_timing", "tutoring"];
const slugOf = (s: any, change: Record<string, string> = {}) => {
  const base = s.settings.find((x: any) => x.default);
  return SLUG_KEYS.map((k) => change[k] ?? base[k]).join("_");
};

function axisOf(start: string, end: string): string[] {
  const out: string[] = [];
  for (let y = +start.slice(0, 4), m = +start.slice(5, 7); ; ) {
    const p = `${y}-${String(m).padStart(2, "0")}`;
    if (p > end) return out;
    out.push(p);
    if (++m > 12) { m = 1; y++; }
  }
}

/** The chart's one-sentence summary, as the page should write it from the file. */
function summaryOf(lang: Lang, file: any, groups: string[], measure: Measure): string {
  const axis = axisOf(file.start, file.end);
  const digits = measure === "index" ? 2 : 1;
  const ends = groups.map((g) => {
    const values: (number | null)[] = file.groups[dataKey(g)][measure];
    let i = values.length - 1;
    while (i > 0 && values[i] === null) i--;
    return { g, i, v: values[i] as number };
  });
  const last = axis[Math.max(...ends.map((e) => e.i))];
  const items = ends.map((e) => t(lang, "summary.item", { value: `${num(lang, e.v, digits)}${measure === "index" ? "" : "%"}`, group: t(lang, `group.in.${e.g}`) }));
  const list = items.length > 1 ? `${items.slice(0, -1).join(", ")} ${t(lang, "summary.and")} ${items.at(-1)}` : items[0];
  return measure === "rch_a"
    ? t(lang, "summary.annual", { month: month(lang, last, lang === "el" ? "acc" : "nom"), list })
    : `${t(lang, `explore.measure.${measure}`)}, ${month(lang, last)}: ${list}.`;
}

const root = (page: Page) => page.locator("#explore");
const summary = (page: Page) => root(page).locator('[data-role="summary"]');
const chip = (page: Page, lang: Lang, g: string) => root(page).getByRole("button", { name: t(lang, `group.${g}`), exact: true });
const params = (page: Page) => new URL(page.url()).searchParams;

async function openOptions(page: Page, lang: Lang = "en") {
  await root(page).locator("summary").filter({ hasText: t(lang, "option.heading") }).click();
}
function radio(page: Page, option: string, value: string): Locator {
  return root(page).locator(`fieldset[data-option="${option}"] input[value="${value}"]`);
}

for (const lang of LANGS) {
  test(`${lang}: the default view's summary is the default setting's latest values`, async ({ page, request }) => {
    const s = await settings(request);
    const file = await series(request, s.default);
    await page.goto(m1(lang, "explore/"));
    await expect(summary(page)).toHaveText(summaryOf(lang, file, DEFAULT_GROUPS, "rch_a"));
    await expect(root(page).locator('[data-role="noscript"]')).toBeHidden();
    for (const g of DEFAULT_GROUPS) await expect(chip(page, lang, g)).toHaveAttribute("aria-pressed", "true");
    await expect(root(page).locator('[data-role="group-count"]')).toHaveText(t(lang, "explore.groups_max", { n: 3, max: 6 }));
    await expect(root(page).locator('[data-role="changed"]')).toHaveText(t(lang, "option.all_defaults"));
    await expect(root(page).locator('[data-role="chart"] svg').first()).toBeVisible();
  });
}

test("the data table lists every month, newest first, with the file's values", async ({ page, request }) => {
  const s = await settings(request);
  const file = await series(request, s.default);
  await page.goto(m1("en", "explore/"));
  await expect(summary(page)).not.toBeEmpty();
  await root(page).locator("summary").filter({ hasText: t("en", "chart.data_points") }).click();
  const table = root(page).getByRole("region", { name: t("en", "chart.data_points") }).locator("table");
  const head = await table.locator("thead th").allTextContents();
  expect(head).toEqual([t("en", "chart.month"), ...DEFAULT_GROUPS.map((g) => t("en", `group.${g}`)), t("en", "gap")]);

  const axis = axisOf(file.start, file.end);
  const lines = DEFAULT_GROUPS.map((g) => file.groups[dataKey(g)].rch_a as (number | null)[]);
  const first = Math.min(...lines.map((l) => l.findIndex((v) => v !== null)).filter((i) => i >= 0));
  const cells = (i: number) => [axis[i], ...[...lines.map((l) => l[i]), file.gaps.B.rch_a[i]].map((v) => (v === null ? "–" : num("en", v, 1)))];
  const rows = table.locator("tbody tr");
  await expect(rows).toHaveCount(axis.length - first);
  expect(await rows.first().locator("th, td").allTextContents()).toEqual(cells(axis.length - 1));
  expect(await rows.last().locator("th, td").allTextContents()).toEqual(cells(first));
});

test("groups toggle on and off, up to six, never none, and go in the address", async ({ page }) => {
  await page.goto(m1("en", "explore/"));
  await chip(page, "en", "Q3").click();
  await expect(chip(page, "en", "Q3")).toHaveAttribute("aria-pressed", "true");
  expect(params(page).get("groups")).toBe("Q1,Q5,all/all,Q3");
  await chip(page, "en", "Q5").click();
  expect(params(page).get("groups")).toBe("Q1,all/all,Q3");

  for (const g of ["Q2", "Q4", "tenure/renter"]) await chip(page, "en", g).click();
  await expect(root(page).locator('[data-role="group-count"]')).toHaveText(t("en", "explore.groups_max", { n: 6, max: 6 }));
  await expect(chip(page, "en", "tenure/owner")).toBeDisabled();

  await page.goto(`${m1("en", "explore/")}?groups=Q2`);
  await chip(page, "en", "Q2").click();                          // the last one stays
  await expect(chip(page, "en", "Q2")).toHaveAttribute("aria-pressed", "true");
});

test("changing an option loads that setting, counts the change, and puts only that in the address", async ({ page, request }) => {
  const s = await settings(request);
  const [option, value] = ["price_source", s.options.price_source.find((v: string) => v !== "cpi")];
  const slug = slugOf(s, { [option]: value });
  const file = await series(request, slug);
  await page.goto(m1("en", "explore/"));
  await openOptions(page);
  const fetched = page.waitForRequest((r) => r.url().endsWith(`/series/${slug}.json`));
  await radio(page, option, value).check();
  await fetched;
  await expect(summary(page)).toHaveText(summaryOf("en", file, DEFAULT_GROUPS, "rch_a"));
  expect(params(page).get(option)).toBe(value);
  for (const k of SLUG_KEYS.filter((k) => k !== option)) expect(params(page).has(k)).toBe(false);
  await expect(root(page).locator('[data-role="changed"]')).toHaveText(t("en", "option.changed", { n: 1 }));
  await radio(page, option, "cpi").check();                      // back to the default: out of the address
  await expect(root(page).locator('[data-role="changed"]')).toHaveText(t("en", "option.all_defaults"));
  expect(params(page).has(option)).toBe(false);
});

test("a shared address opens the same view; unknown values fall back to the defaults", async ({ page, request }) => {
  const s = await settings(request);
  await page.goto(`${m1("en", "explore/")}?price_source=hicp&weights_timing=U&groups=Q1,tenure/renter&m=index&gap=0`);
  await expect(radio(page, "price_source", "hicp")).toBeChecked();
  await expect(radio(page, "weights_timing", "U")).toBeChecked();
  await expect(chip(page, "en", "tenure/renter")).toHaveAttribute("aria-pressed", "true");
  await expect(chip(page, "en", "Q5")).toHaveAttribute("aria-pressed", "false");
  await expect(root(page).locator('[data-role="measure"]')).toHaveValue("index");
  const file = await series(request, slugOf(s, { price_source: "hicp", weights_timing: "U" }));
  await expect(summary(page)).toHaveText(summaryOf("en", file, ["Q1", "tenure/renter"], "index"));
  // The timing rule leaves months out: the chart says so.
  await expect(root(page).locator('[data-role="notice"]')).toBeVisible();

  await page.goto(`${m1("en", "explore/")}?price_source=nope&groups=nope&m=nope`);
  await expect(radio(page, "price_source", "cpi")).toBeChecked();
  await expect(summary(page)).toHaveText(summaryOf("en", await series(request, s.default), DEFAULT_GROUPS, "rch_a"));
});

test("an option that can't be had is greyed, with its reason", async ({ page }) => {
  await page.goto(m1("en", "explore/"));
  await openOptions(page);
  await expect(radio(page, "imputed_rent", "user_cost")).toBeDisabled();
  const reason = t("en", "option.unavailable", { reason: t("en", "reason.user_cost") });
  await expect(root(page).locator('fieldset[data-option="imputed_rent"]')).toContainText(reason);
});

test("the measure changes the summary; the gap panel is for the annual rate only", async ({ page, request }) => {
  const s = await settings(request);
  const file = await series(request, s.default);
  await page.goto(m1("en", "explore/"));
  const gap = root(page).getByLabel(t("en", "explore.gap_toggle"));
  await expect(root(page).locator('[data-role="gap-title"]')).toBeVisible();
  for (const m of ["rch_m", "index"] as const) {
    await root(page).locator('[data-role="measure"]').selectOption(m);
    await expect(summary(page)).toHaveText(summaryOf("en", file, DEFAULT_GROUPS, m));
    expect(params(page).get("m")).toBe(m);
    await expect(gap).toBeDisabled();
    await expect(root(page).locator('[data-role="gap-reason"]')).toHaveText(t("en", "explore.gap_annual_only"));
  }
  await root(page).locator('[data-role="measure"]').selectOption("rch_a");
  expect(params(page).has("m")).toBe(false);
  await gap.uncheck();
  expect(params(page).get("gap")).toBe("0");
  await expect(root(page).locator('[data-role="gap-title"]')).toBeHidden();
});

test("the gap note shows when the poorest or richest fifth isn't drawn", async ({ page }) => {
  await page.goto(`${m1("en", "explore/")}?groups=Q1,all/all`);
  await expect(root(page).locator('[data-role="gap-note"]')).toBeVisible();
});

test.describe("the breakdown view", () => {
  test("one group: its latest rate, split by category, with the rest folded", async ({ page, request }) => {
    const s = await settings(request);
    const c = await json(request, `${DATA}/contributions/${s.default}.json`);
    const byMonth = c.groups["B/Q1"];
    const parts: Record<string, number> = byMonth[Object.keys(byMonth).sort().at(-1)!];
    const total = Object.values(parts).reduce((a, v) => a + v, 0);
    await page.goto(`${m1("en", "explore/")}?groups=Q1`);
    await root(page).getByRole("button", { name: t("en", "explore.view.parts") }).click();
    expect(params(page).get("view")).toBe("parts");
    await expect(root(page).locator('[data-role="contrib-title"]')).toHaveText(
      t("en", "explore.contrib_title", { group: t("en", "group.in.Q1"), value: `${num("en", total)}%` }));
    await expect(root(page).locator('[data-role="measure"]')).toBeDisabled();
    await expect(root(page).locator('[data-role="measure-reason"]')).toBeVisible();
    await expect(root(page).locator('[data-role="summary"]')).toBeHidden();

    const rows = root(page).locator('[data-role="bars"] > .contrib-line');
    const n = Object.keys(parts).length;
    await expect(rows).toHaveCount(n);
    if (n > 5) {
      await expect(rows.nth(5)).toBeHidden();
      const more = root(page).locator('[data-role="contrib-more"]');
      await expect(more).toHaveText(t("en", "explore.contrib_all", { n }));
      await more.click();
      await expect(more).toHaveAttribute("aria-expanded", "true");
      await expect(rows.nth(5)).toBeVisible();
    }
  });

  test("two groups: a difference line per category, and the gap between them", async ({ page }) => {
    await page.goto(`${m1("en", "explore/")}?groups=Q1,Q5&view=parts`);
    await expect(root(page).getByRole("button", { name: t("en", "explore.view.parts") })).toHaveAttribute("aria-pressed", "true");
    await expect(root(page).locator('[data-role="contrib-title"]')).toHaveText(t("en", "explore.contrib_title_many"));
    await expect(root(page).locator(".contrib-row.total .diff")).toHaveCount(1);
    await expect(root(page).locator('[data-role="contrib-note"]')).toContainText(t("en", "group.in.Q1"));
    // Back to the series over time.
    await root(page).getByRole("button", { name: t("en", "explore.view.time") }).click();
    expect(params(page).has("view")).toBe(false);
    await expect(summary(page)).toBeVisible();
  });
});

test("the files link and the citation follow the setting", async ({ page, request }) => {
  const s = await settings(request);
  await page.goto(m1("en", "explore/"));
  const files = root(page).locator('[data-role="files-this"]');
  await expect(files).toHaveAttribute("href", new RegExp(`#setting-${s.default}$`));
  await openOptions(page);
  await radio(page, "tutoring", "excluded").check();
  await expect(files).toHaveAttribute("href", new RegExp(`#setting-${slugOf(s, { tutoring: "excluded" })}$`));
  const cite = root(page).locator('[data-role="cite"]');
  await expect(cite).toContainText(page.url());
  await expect(cite).toContainText(t("en", "option.tutoring.excluded"));
});

test.describe("when a file can't be loaded", () => {
  // The browser itself logs the refused request; that's the point of this test.
  test.use({ allowErrors: [/Failed to load resource/] });

  test("the chart says so, and Retry tries again", async ({ page }) => {
    await page.route("**/series/*.json", (route) => route.fulfill({ status: 503, body: "" }));
    await page.goto(m1("en", "explore/"));
    const failed = root(page).getByRole("alert");
    await expect(failed).toContainText(t("en", "chart.failed"));
    await page.unroute("**/series/*.json");
    await failed.getByRole("button", { name: t("en", "chart.retry") }).click();
    await expect(failed).toBeHidden();
    await expect(summary(page)).not.toBeEmpty();
  });
});

test("full screen shows the chart alone, and the button says how to leave", async ({ page }) => {
  await page.goto(m1("en", "explore/"));
  const button = root(page).locator('[data-role="fullscreen"]');
  test.skip(!(await page.evaluate(() => document.fullscreenEnabled)), "this browser offers no full screen");
  await button.click();
  await expect(button).toHaveAttribute("aria-label", t("en", "chart.fullscreen_exit"));
  await button.click();
  await expect(button).toHaveAttribute("aria-label", t("en", "chart.fullscreen"));
});
