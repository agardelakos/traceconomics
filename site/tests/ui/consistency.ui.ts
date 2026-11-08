// The consistency topic: the overview of every check, a check's page with its differences, a
// written finding, a question across sources, and the ways in (the country card, the Groups page,
// the data page). Expected values come from the published checks.json, not from the page.
import { expect, gwt, num, t, test } from "./helpers";

const M5 = (lang: string, rest = "") => `/${lang}/gr/official-figures-consistency/${rest}`;
const DATA = "/data/v1/gr/m5/latest";

function status(c: any): string {
  const unknown = c.differ["not-known"] ?? 0;
  const differ = c.compared - c.agree;
  return differ === 0 ? "agree" : unknown === 0 ? "explained" : unknown < differ ? "partly" : "unknown";
}

for (const lang of ["en", "el"] as const) {
  test(`the overview lists every check with how often it agrees and where it stands (${lang})`, gwt({
    id: "PW-M5-001",
    title: "the overview lists every check with how often it agrees and where it stands",
    given: "the consistency topic's overview for Greece, in English or Greek",
    when: "it is opened",
    then: ["its heading is the topic's question", "there is one row per check in checks.json, in its order",
      "each row gives \"N of M match\" and the check's status, and links to the check's page"],
  }), async ({ page, request }) => {
    const r = await (await request.get(`${DATA}/checks.json`)).json();
    await page.goto(M5(lang));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(t(lang, "topic.official-figures-consistency.question"));
    const rows = page.locator('[data-m5="checks"] tbody tr');
    await expect(rows).toHaveCount(r.checks.length);
    for (const [i, c] of r.checks.entries()) {
      const row = rows.nth(i);
      await expect(row.getByRole("link", { name: t(lang, `m5.check.${c.id}.title`) }))
        .toHaveAttribute("href", M5(lang, `checks/${c.id.slice(3)}/`));
      await expect(row).toContainText(t(lang, "m5.count", { agree: c.agree, compared: c.compared }));
      await expect(row.locator(".chip-status")).toHaveText(t(lang, `m5.status.${status(c)}`));
    }
  });
}

test("a check's page lists each difference with its cause and offers every period as CSV", gwt({
  id: "PW-M5-002",
  given: "the page of the check of the CPI's rates against its own index",
  when: "it is opened and its download link is followed",
  then: ["it gives the check's count", "its table has one row per difference, each with its cause",
    "it links to the finding with its own page", "the download is the check's CSV, with a header and one row per period compared"],
}), async ({ page, request }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  const c = r.checks.find((x: any) => x.id === "gr-cpi-rates-own-index");
  await page.goto(M5("en", "checks/cpi-rates-own-index/"));
  await expect(page.locator('[data-m5="count"]')).toContainText(t("en", "m5.count", { agree: c.agree, compared: c.compared }));
  const rows = page.locator('[data-m5="differences"] tbody tr');
  await expect(rows).toHaveCount(c.differences.length);
  for (const [i, d] of c.differences.entries()) await expect(rows.nth(i).locator("td").last()).toHaveText(t("en", `m5.cat.${d.explanation}`));
  await expect(page.locator('a.card[href$="/june-2001/"]')).toBeVisible();
  const href = await page.getByRole("link", { name: t("en", "m5.download") }).getAttribute("href");
  expect(href).toBe(`${DATA}/downloads/gr-cpi-rates-own-index.csv`);
  const csv = (await (await request.get(href!)).text()).trim().split("\n");
  expect(csv[0]).toBe("period,published,rebuilt,difference,agree,explanation,finding");
  expect(csv.length - 1).toBe(c.compared);
});

test("a finding's page tells what happened, links back to its check and lists its sources", gwt({
  id: "PW-M5-003",
  given: "the June 2001 finding's page, reached from its check",
  when: "it is opened and its sources are unfolded",
  then: ["its heading is the finding's title", "it links back to the check's page", "its sources list is not empty"],
}), async ({ page, coverage }) => {
  await page.goto(M5("en", "checks/cpi-rates-own-index/"));
  await coverage.flush();
  await page.locator('a.card[href$="/june-2001/"]').click();
  await expect(page).toHaveURL(/\/checks\/cpi-rates-own-index\/june-2001\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("June 2001");
  await expect(page.getByRole("link", { name: t("en", "m5.check.gr-cpi-rates-own-index.title") }))
    .toHaveAttribute("href", M5("en", "checks/cpi-rates-own-index/"));
  await page.locator("details.panel summary", { hasText: t("en", "m5.finding.sources") }).click();
  await expect(page.locator("ol.sources li").first()).toBeVisible();
});

test("a question across sources lines up each source's value by year, reached from the Groups page", gwt({
  id: "PW-M5-004",
  given: "the Groups page for Greece, whose two income limits are for the same year",
  when: "its link to every year is followed",
  then: ["the question's page opens", "its table has a row per income year with both sources' poorest-fifth limits and the gap",
    "the values match checks.json"],
}), async ({ page, request, coverage }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  const q = r.questions.find((x: any) => x.id === "gr-income-limits");
  await page.goto("/en/gr/inflation-by-group/groups/");
  await coverage.flush();
  await page.locator('[data-income-role="compare-link"] a').click();
  await expect(page).toHaveURL(/\/same-question\/income-limits\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(t("en", "m5.question.gr-income-limits.title"));
  const years = [...new Set(Object.keys(q.values.hbs).map((p: string) => p.split("/")[0]))]
    .filter((y) => q.values.hbs[`${y}/Q1`] != null || q.values.silc[`${y}/Q1`] != null).sort();
  const rows = page.locator('[data-m5="question"] tbody tr');
  await expect(rows).toHaveCount(years.length);
  const last = years[years.length - 1];
  const a = q.values.hbs[`${last}/Q1`], b = q.values.silc[`${last}/Q1`];
  const row = rows.last();
  await expect(row.locator("th")).toHaveText(last);
  await expect(row.locator("td").nth(0)).toHaveText(a == null ? "–" : num("en", a, 0));
  await expect(row.locator("td").nth(1)).toHaveText(b == null ? "–" : num("en", b, 0));
});

test("the home page's country card and the data page lead to the topic and its files", gwt({
  id: "PW-M5-005",
  given: "the home page and Greece's data page",
  when: "each is opened",
  then: ["Greece's card links to the consistency topic", "the data page has a section for the topic listing checks.json and each check's CSV",
    "every file listed there answers with success"],
}), async ({ page, request }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  await page.goto("/en/");
  await expect(page.locator('[data-m5="card-link"] a')).toHaveAttribute("href", M5("en"));
  await page.goto("/en/data/gr/");
  const links = page.locator('[data-m5="files"] a');
  await expect(links).toHaveCount(2 + r.checks.length + r.questions.length);
  for (const href of await links.evaluateAll((as) => as.map((a) => a.getAttribute("href")!))) {
    expect((await request.get(href)).status(), href).toBe(200);
  }
});

test("a question across several sources gives each source's value by year, its definition, and AADE's figures as published", gwt({
  id: "PW-M5-006",
  given: "the rent-paid question's page for Greece",
  when: "it is opened",
  then: ["its table has one column per source and one row per year in checks.json, values in billions of euros",
    "each source's definition is listed", "AADE's figures are also given exactly as published"],
}), async ({ page, request }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  const q = r.questions.find((x: any) => x.id === "gr-rent-paid");
  await page.goto(M5("en", "same-question/rent-paid/"));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(t("en", "m5.question.gr-rent-paid.title"));
  const table = page.locator('[data-m5="question"]');
  await expect(table.locator("thead th")).toHaveCount(1 + q.sources.length);
  const periods = [...new Set(q.sources.flatMap((s: any) => Object.keys(q.values[s.label])))].sort() as string[];
  await expect(table.locator("tbody tr")).toHaveCount(periods.length);
  const na = q.sources.findIndex((s: any) => s.label === "national_accounts");
  const row = table.locator("tbody tr").filter({ has: page.locator("th", { hasText: periods[0] }) });
  const v = q.values.national_accounts[periods[0]];
  await expect(row.locator("td").nth(na)).toHaveText(v == null ? "–" : num("en", v / 1e9, 2));
  await expect(page.locator('[data-m5="definitions"] dd')).toHaveCount(q.sources.length);
  const aade = Object.entries(q.values.aade).filter(([, x]) => x != null);
  await expect(page.locator('[data-m5="as-published"] li')).toHaveCount(aade.length);
  await expect(page.locator('[data-m5="as-published"] li').first()).toContainText(num("en", aade[0][1] as number, 2));
});
