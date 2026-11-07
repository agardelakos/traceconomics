// Explore: the groups, options, measure, gap and view live in the address, so a shared link opens
// the same view; the chart's summary, its data table, the breakdown, the files link and the
// citation follow the choice. Expected numbers come from the published files for that setting.
import type { APIRequestContext, Locator, Page } from "@playwright/test";
import { expect, gwt, json, LANGS, m1, month, num, t, test, type Lang } from "./helpers";

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
  test(`${lang}: the default view's summary is the default setting's latest values`, gwt({
    id: "PW-EXPL-001",
    given: "Explore, opened with nothing chosen",
    when: "the chart is drawn",
    then: ["its one-sentence summary gives the default setting's latest annual rates for the poorest fifth, the richest fifth and all households, for their month",
      "those three groups are shown as picked, with a count of 3 of at most 6", "it says every option is at its default",
      "the chart is drawn, and no no-script message is shown"],
  }), async ({ page, request }) => {
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

test("the data table lists every month, newest first, with the file's values", gwt({
  id: "PW-EXPL-002",
  given: "Explore at its default view",
  when: "its data table is opened",
  then: ["the table's columns are the month, each default group and the gap",
    "it has one row per month from the first month any group has a value to the latest",
    "the first row is the newest month and the last row the oldest, each with the published file's values (a dash where there is none)"],
}), async ({ page, request }) => {
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

test("groups toggle on and off, up to six, never none, and go in the address", gwt({
  id: "PW-EXPL-003",
  given: "Explore at its default view",
  when: ["the middle fifth is picked, then the richest fifth is unpicked", "three more groups are picked, making six"],
  then: ["the middle fifth shows as pressed and is added at the end of the address's list of groups",
    "the richest fifth leaves that list", "with six groups the count says 6 of 6 and the other groups can't be picked"],
}), async ({ page }) => {
  await page.goto(m1("en", "explore/"));
  await chip(page, "en", "Q3").click();
  await expect(chip(page, "en", "Q3")).toHaveAttribute("aria-pressed", "true");
  expect(params(page).get("groups")).toBe("Q1,Q5,all/all,Q3");
  await chip(page, "en", "Q5").click();
  expect(params(page).get("groups")).toBe("Q1,all/all,Q3");

  for (const g of ["Q2", "Q4", "tenure/renter"]) await chip(page, "en", g).click();
  await expect(root(page).locator('[data-role="group-count"]')).toHaveText(t("en", "explore.groups_max", { n: 6, max: 6 }));
  await expect(chip(page, "en", "tenure/owner")).toBeDisabled();
});

test("the last group can't be unpicked", gwt({
  id: "PW-EXPL-021",
  given: "Explore opened with one group only, the second fifth",
  when: "that group is pressed",
  then: "it stays picked",
}), async ({ page }) => {
  await page.goto(`${m1("en", "explore/")}?groups=Q2`);
  await expect(chip(page, "en", "Q2")).toHaveAttribute("aria-pressed", "true");
  await chip(page, "en", "Q2").click();
  await expect(chip(page, "en", "Q2")).toHaveAttribute("aria-pressed", "true");
});

test("changing an option loads that setting, counts the change, and puts only that in the address", gwt({
  id: "PW-EXPL-004",
  given: "Explore at its default view, with its options open",
  when: ["a price source other than the default is picked", "the default price source is picked again"],
  then: ["that setting's file is loaded and the summary gives its latest annual rates",
    "the address carries that option and no other", "it says one option is changed",
    "back at the default, it says every option is at its default and the option leaves the address"],
}), async ({ page, request }) => {
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

test("a shared address opens the same view", gwt({
  id: "PW-EXPL-005",
  given: "an address naming a price source, a weights timing, two groups, the index as the measure and the gap off",
  when: "Explore opens from it",
  then: ["the named options are chosen, the named groups are picked and no others from the defaults", "the measure is the index",
    "the gap is off, and the address still says so (`gap=0`)",
    "the summary gives that setting's latest index values for those groups",
    "a notice says months are left out (the timing rule's effect)"],
}), async ({ page, request }) => {
  const s = await settings(request);
  await page.goto(`${m1("en", "explore/")}?price_source=hicp&weights_timing=U&groups=Q1,tenure/renter&m=index&gap=0`);
  await expect(radio(page, "price_source", "hicp")).toBeChecked();
  await expect(radio(page, "weights_timing", "U")).toBeChecked();
  await expect(chip(page, "en", "tenure/renter")).toHaveAttribute("aria-pressed", "true");
  await expect(chip(page, "en", "Q5")).toHaveAttribute("aria-pressed", "false");
  await expect(root(page).locator('[data-role="measure"]')).toHaveValue("index");
  await expect(root(page).getByLabel(t("en", "explore.gap_toggle"))).not.toBeChecked();
  expect(params(page).get("gap")).toBe("0");
  const file = await series(request, slugOf(s, { price_source: "hicp", weights_timing: "U" }));
  await expect(summary(page)).toHaveText(summaryOf("en", file, ["Q1", "tenure/renter"], "index"));
  // The timing rule leaves months out: the chart says so.
  await expect(root(page).locator('[data-role="notice"]')).toBeVisible();
});

test("unknown values in a shared address fall back to the defaults", gwt({
  id: "PW-EXPL-015",
  given: "an address whose price source, groups and measure are unknown",
  when: "Explore opens from it",
  then: ["the default price source is chosen", "the three default groups are picked", "the measure is the annual rate",
    "the summary is the default view's", "the address drops the unknown price source and measure"],
}), async ({ page, request }) => {
  const s = await settings(request);
  await page.goto(`${m1("en", "explore/")}?price_source=nope&groups=nope&m=nope`);
  await expect(radio(page, "price_source", "cpi")).toBeChecked();
  for (const g of DEFAULT_GROUPS) await expect(chip(page, "en", g)).toHaveAttribute("aria-pressed", "true");
  await expect(root(page).locator('[data-role="measure"]')).toHaveValue("rch_a");
  await expect(summary(page)).toHaveText(summaryOf("en", await series(request, s.default), DEFAULT_GROUPS, "rch_a"));
  await expect.poll(() => [params(page).get("price_source"), params(page).get("m")]).toEqual([null, null]);
});

test("an option Greece can't have is not offered", gwt({
  id: "PW-EXPL-006",
  given: "Explore, with its options open",
  when: "the imputed-rent options are read",
  then: "user cost is not offered",
}), async ({ page }) => {
  // Imputed rent by user cost needs a price index Greece doesn't publish: the method page explains it.
  await page.goto(m1("en", "explore/"));
  await openOptions(page);
  await expect(radio(page, "imputed_rent", "user_cost")).toHaveCount(0);
});

test("an old link asking for an option Greece can't have falls back to the default", gwt({
  id: "PW-EXPL-016",
  given: "an address asking for imputed rent by user cost",
  when: "Explore opens from it",
  then: ["imputed rent is excluded (the default)", "the summary is drawn", "the option leaves the address"],
}), async ({ page }) => {
  await page.goto(`${m1("en", "explore/")}?imputed_rent=user_cost`);
  await expect(radio(page, "imputed_rent", "excluded")).toBeChecked();
  await expect(summary(page)).not.toBeEmpty();
  await expect.poll(() => params(page).get("imputed_rent")).toBeNull();
});

for (const m of ["rch_m", "index"] as const) {
  test(`the ${m} measure changes the summary, and the gap is for the annual rate only`, gwt({
    id: "PW-EXPL-007",
    title: "another measure changes the summary; the gap is for the annual rate only",
    given: "Explore at its default view, with the gap panel shown",
    when: "the measure is set to the monthly rate or the index",
    then: ["the summary gives that measure's latest values", "the address carries the measure",
      "the gap switch is disabled, with a reason saying it is for the annual rate only"],
  }), async ({ page, request }) => {
    const s = await settings(request);
    const file = await series(request, s.default);
    await page.goto(m1("en", "explore/"));
    await expect(root(page).locator('[data-role="gap-title"]')).toBeVisible();
    await root(page).locator('[data-role="measure"]').selectOption(m);
    await expect(summary(page)).toHaveText(summaryOf("en", file, DEFAULT_GROUPS, m));
    expect(params(page).get("m")).toBe(m);
    await expect(root(page).getByLabel(t("en", "explore.gap_toggle"))).toBeDisabled();
    await expect(root(page).locator('[data-role="gap-reason"]')).toHaveText(t("en", "explore.gap_annual_only"));
  });
}

test("back at the annual rate, the measure leaves the address", gwt({
  id: "PW-EXPL-017",
  given: "Explore opened with the index as the measure",
  when: "the measure is set back to the annual rate",
  then: ["the measure leaves the address", "the gap switch can be used again"],
}), async ({ page }) => {
  await page.goto(`${m1("en", "explore/")}?m=index`);
  await expect(root(page).locator('[data-role="measure"]')).toHaveValue("index");
  await root(page).locator('[data-role="measure"]').selectOption("rch_a");
  await expect.poll(() => params(page).has("m")).toBe(false);
  await expect(root(page).getByLabel(t("en", "explore.gap_toggle"))).toBeEnabled();
});

test("with the gap off, the address says so and the gap panel is hidden", gwt({
  id: "PW-EXPL-018",
  given: "Explore at its default view, with the gap panel shown",
  when: "the gap is turned off",
  then: ["the address says so (`gap=0`)", "the gap panel is hidden"],
}), async ({ page }) => {
  await page.goto(m1("en", "explore/"));
  await expect(root(page).locator('[data-role="gap-title"]')).toBeVisible();
  await root(page).getByLabel(t("en", "explore.gap_toggle")).uncheck();
  expect(params(page).get("gap")).toBe("0");
  await expect(root(page).locator('[data-role="gap-title"]')).toBeHidden();
});

test("each of the six household types is offered as a group", gwt({
  id: "PW-EXPL-022",
  given: "Explore at its default view",
  when: "its groups are read",
  then: "a button is shown for each of the six household types",
}), async ({ page }) => {
  await page.goto(m1("en", "explore/"));
  for (const g of ["hhtype/A1", "hhtype/A1_DCH", "hhtype/A2", "hhtype/A2_DCH", "hhtype/A_GE3", "hhtype/A_GE3_DCH"]) {
    await expect(chip(page, "en", g)).toBeVisible();
  }
});

test("household types are a family of their own: each draws its line from the file", gwt({
  id: "PW-EXPL-008",
  given: "an address picking two household types",
  when: "Explore opens from it",
  then: ["the summary gives those two household types' latest annual rates from the published file",
    "the second one is shown as picked"],
}), async ({ page, request }) => {
  const s = await settings(request);
  const file = await series(request, s.default);
  await page.goto(`${m1("en", "explore/")}?groups=${encodeURIComponent("hhtype/A1,hhtype/A2_DCH")}`);
  await expect(summary(page)).toHaveText(summaryOf("en", file, ["hhtype/A1", "hhtype/A2_DCH"], "rch_a"));
  await expect(chip(page, "en", "hhtype/A2_DCH")).toHaveAttribute("aria-pressed", "true");
});

test("the gap note shows when the poorest or richest fifth isn't drawn", gwt({
  id: "PW-EXPL-009",
  given: "an address picking the poorest fifth and all households, but not the richest fifth",
  when: "Explore opens from it",
  then: "the note about the gap is shown",
}), async ({ page }) => {
  await page.goto(`${m1("en", "explore/")}?groups=Q1,all/all`);
  await expect(root(page).locator('[data-role="gap-note"]')).toBeVisible();
});

test.describe("the breakdown view", () => {
  test("one group: its latest rate, split by category, with the rest folded", gwt({
    id: "PW-EXPL-010",
    given: "Explore with the poorest fifth alone",
    when: ["the breakdown view is chosen", "the button to show every category is pressed (when there are more than five)"],
    then: ["the address carries the view",
      "the title gives the group's latest annual rate, the sum of its categories' parts in the published file",
      "the measure can't be changed, with a reason shown, and the summary is hidden", "there is one line per category",
      "beyond five categories, the sixth on is folded away until the button (which gives the number of categories) is pressed, and then shown"],
  }), async ({ page, request }) => {
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

  test("two groups: a difference line per category, and the gap between them", gwt({
    id: "PW-EXPL-011",
    given: "an address opening Explore's breakdown view for the poorest and richest fifths",
    when: ["it opens", "the view over time is chosen again"],
    then: ["the breakdown view is shown as chosen, with the title for several groups", "the total row shows one difference",
      "the note under it names the poorest fifth", "back over time, the view leaves the address and the summary is shown"],
  }), async ({ page }) => {
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

test("the files link and the citation follow the setting", gwt({
  id: "PW-EXPL-012",
  given: "Explore at its default view",
  when: ["its options are opened and private tutoring is excluded"],
  then: ["the link to this view's files points first at the default setting's files, then at the new setting's",
    "the citation holds the page's current address and names the changed option"],
}), async ({ page, request }) => {
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

  test("the chart says so, and Retry tries again", gwt({
    id: "PW-EXPL-013",
    given: "the chart's data files answer with an error",
    when: ["Explore opens", "the files answer again and Retry is pressed"],
    then: ["the chart shows an alert saying the data couldn't be loaded, with a Retry button",
      "after Retry, the alert goes and the summary is drawn"],
  }), async ({ page }) => {
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

test("full screen shows the chart alone, and the button says how to leave", gwt({
  id: "PW-EXPL-014",
  given: "Explore, in a browser that offers full screen",
  when: ["the full-screen button is pressed", "it is pressed again"],
  then: ["the chart's figure fills the screen, without the groups or the options",
    "the button's name changes to say how to leave full screen",
    "pressed again, full screen ends and the button goes back to its first name"],
}), async ({ page }) => {
  await page.goto(m1("en", "explore/"));
  const button = root(page).locator('[data-role="fullscreen"]');
  test.skip(!(await page.evaluate(() => document.fullscreenEnabled)), "this browser offers no full screen");
  await button.click();
  await expect.poll(() => page.evaluate(() => document.fullscreenElement?.getAttribute("data-role") ?? null)).toBe("chart-figure");
  // The chart alone: the group buttons and the options stay outside what fills the screen.
  expect(await page.evaluate(() => document.fullscreenElement!.querySelectorAll("button.chip, fieldset[data-option]").length)).toBe(0);
  await expect(page.locator('#explore [data-role="chart"]')).toBeVisible();
  await expect(button).toHaveAttribute("aria-label", t("en", "chart.fullscreen_exit"));
  await button.click();
  await expect.poll(() => page.evaluate(() => document.fullscreenElement === null)).toBe(true);
  await expect(button).toHaveAttribute("aria-label", t("en", "chart.fullscreen"));
});

test("following the files link opens the data page with the setting's box open", gwt({
  id: "PW-EXPL-019",
  given: "Explore at its default view",
  when: "the link to this view's files is unfolded and followed",
  then: ["the browser goes to the data page for Greece, at the default setting's box", "that box is open, with files to download"],
}), async ({ page, request, coverage }) => {
  const s = await settings(request);
  await page.goto(m1("en", "explore/"));
  await root(page).locator('details:has([data-role="files-this"]) > summary').click();
  await coverage.flush();
  await root(page).locator('[data-role="files-this"]').click();
  await expect(page).toHaveURL(new RegExp(`/en/data/gr/#setting-${s.default}$`));
  const box = page.locator(`details#setting-${s.default}`);
  await expect(box).toHaveAttribute("open", "");
  expect(await box.locator("a[download]").count()).toBeGreaterThan(0);
});

test("months an option leaves out are noted, with the reason", gwt({
  id: "PW-EXPL-020",
  given: "Explore at its default view, and weights timing rule F, which leaves out months before its first survey",
  when: "rule F is chosen",
  then: ["a notice above the chart gives the reason, as the availability file names it", "the option's own note gives the same reason"],
}), async ({ page, request }) => {
  const greyed: { reason: string }[] = (await json(request, `${DATA}/availability.json`)).options.weights_timing.F.greyed;
  const reasons = greyed.map((g) => t("en", `reason.${g.reason}`));
  expect(reasons.length, "the data have no months rule F leaves out: nothing to check").toBeGreaterThan(0);
  await page.goto(m1("en", "explore/"));
  const notice = root(page).locator('[data-role="notice"]');
  await expect(notice).toBeHidden();
  await openOptions(page);
  await radio(page, "weights_timing", "F").check();
  await expect(notice).toBeVisible();
  await expect(notice.locator("span")).toHaveText(reasons.join(" "));
  const note = root(page).locator('fieldset[data-option="weights_timing"] [data-role="note"]');
  for (const r of reasons) await expect(note).toContainText(r);
});
