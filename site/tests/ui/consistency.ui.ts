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

const ORDER = ["explained", "partly", "unknown", "agree"];
const byStatus = (checks: any[]) => ORDER.flatMap((st) => checks.filter((c) => status(c) === st));

for (const lang of ["en", "el"] as const) {
  test(`the overview gives three numbers and every check as a card, explained first (${lang})`, gwt({
    id: "PW-M5-001",
    title: "the overview gives three numbers and every check as a card, explained first",
    given: "the consistency topic's overview for Greece, in English or Greek",
    when: "it is opened",
    then: ["its heading is the topic's question",
      "it gives the number of checks, the figures compared with the years they span, and the share that agree, rounded down",
      "there is one card per check in checks.json: explained first, then partly explained, reason not known yet, consistent, each group in file order",
      "each card asks its question in plain words, linking to the check's page, with its status, \"N of M match\" and the years actually checked"],
  }), async ({ page, request }) => {
    const r = await (await request.get(`${DATA}/checks.json`)).json();
    await page.goto(M5(lang));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(t(lang, "topic.official-figures-consistency.question"));
    const sum = (k: string) => r.checks.reduce((n: number, c: any) => n + c[k], 0);
    const years = r.checks.flatMap((c: any) => Object.keys(c.by_year)).sort();
    const stats = page.locator('[data-m5="stats"] p');
    await expect(stats.nth(0).locator("strong")).toHaveText(num(lang, r.checks.length, 0));
    await expect(stats.nth(1).locator("strong")).toHaveText(num(lang, sum("compared"), 0));
    await expect(stats.nth(1)).toContainText(t(lang, "m5.stat.compared", { from: years[0], to: years[years.length - 1] }));
    await expect(stats.nth(2).locator("strong")).toHaveText(`${Math.floor((sum("agree") / sum("compared")) * 100)}%`);
    const cards = page.locator('[data-m5="checks"] [data-m5-card]');
    await expect(cards).toHaveCount(r.checks.length);
    for (const [i, c] of byStatus(r.checks).entries()) {
      const card = cards.nth(i);
      await expect(card).toHaveAttribute("data-m5-card", c.id);
      await expect(card.locator("a.title")).toHaveText(`${t(lang, `m5.check.${c.id}.question`)} →`);
      await expect(card.locator("a.title")).toHaveAttribute("href", M5(lang, `checks/${c.id.slice(3)}/`));
      await expect(card.locator(".chip-status")).toHaveText(t(lang, `m5.status.${status(c)}`));
      await expect(card.locator('[data-m5="count"]')).toHaveText(t(lang, "m5.count", { agree: num(lang, c.agree, 0), compared: num(lang, c.compared, 0) }));
      const span = Object.keys(c.by_year).sort();
      await expect(card).toContainText(t(lang, "m5.checked", { from: span[0], to: span[span.length - 1] }));
    }
  });
}

test("a check's page lists each difference with its cause and offers every period as CSV", gwt({
  id: "PW-M5-002",
  given: "the page of the check of the CPI's rates against its own index",
  when: "it is opened and its download link is followed",
  then: ["it gives the check's count", "its table of what was compared joins the years where all agree and sums to the count",
    "its table has one row per difference, each with its cause",
    "it links to the finding with its own page", "it leads to the topic's section of the Data page, which lists the check's CSV",
    "the CSV has a header and one row per period compared"],
}), async ({ page, request }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  const c = r.checks.find((x: any) => x.id === "gr-cpi-rates-own-index");
  await page.goto(M5("en", "checks/cpi-rates-own-index/"));
  await expect(page.locator('[data-m5="count"]')).toContainText(t("en", "m5.count", { agree: c.agree, compared: c.compared }));
  const rows = page.locator('[data-m5="differences"] tbody tr');
  await expect(rows).toHaveCount(c.differences.length);
  for (const [i, d] of c.differences.entries()) await expect(rows.nth(i).locator("td").last()).toHaveText(t("en", `m5.cat.${d.explanation}`));
  const years = Object.keys(c.by_year).sort();
  const compared = page.locator('[data-m5="compared"] tbody tr');
  await expect(compared.first().locator("th")).toHaveText(new RegExp(`^${years[0]}`));
  const counts = await compared.locator("td:nth-child(2)").allTextContents();
  expect(counts.reduce((n, x) => n + Number(x.replace(/\D/g, "")), 0)).toBe(c.compared);
  await expect(page.locator('a.card[href$="/june-2001/"]')).toBeVisible();
  await expect(page.locator('[data-m5="files"] a')).toHaveAttribute("href", "/en/data/gr/#official-figures-consistency");
  await page.goto("/en/data/gr/");
  const href = `${DATA}/downloads/gr-cpi-rates-own-index.csv`;
  await expect(page.locator(`[data-m5="files"] a[href="${href}"]`)).toHaveCount(1);
  const csv = (await (await request.get(href)).text()).trim().split("\n");
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
    "pointing at each source's name in the table's header opens what it counts", "AADE's figures are also given exactly as published, one row a year",
    "the notice of each publisher whose terms ask for one (AADE, the European Commission) is shown, and no other"],
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
  for (const src of q.sources) {
    const term = table.locator(`th[data-m5-source="${src.label}"] button.term`);
    await expect(term).toHaveText(t("en", `m5.src.gr-rent-paid.${src.label}`));
  }
  const first = table.locator(`th[data-m5-source="${q.sources[0].label}"]`);
  await first.locator("button.term").hover();          // with a mouse, pointing opens it (a click follows its link)
  await expect(first.locator(".term-popover")).toBeVisible();
  await expect(first.locator(".term-popover")).toContainText(t("en", `m5.def.gr-rent-paid.${q.sources[0].label}`));
  await page.mouse.move(0, 0);
  const aade = Object.entries(q.values.aade).filter(([, x]) => x != null);
  const published = page.locator('[data-m5="as-published"] tbody tr');
  await expect(published).toHaveCount(aade.length);
  await expect(published.first().locator("td")).toHaveText(num("en", aade[0][1] as number, 2));
  const notices = ["aade", "ec-empl"].filter((p) => q.sources.some((s: any) => s.source.startsWith(`${p}:`)));
  expect(notices).toContain("aade");
  await expect(page.locator('[data-m5="notice"]')).toHaveText(notices.map((p) => t("en", `m5.notice.${p}`)));
});

test("a question's chart draws every source's values, to scale, without joining years apart", gwt({
  id: "PW-M5-007",
  given: "the renters question's page for Greece",
  when: "it is opened",
  then: ["its chart has an accessible label naming the question and its unit", "the legend lists every source in order",
    "there is one dot per value in checks.json", "a line joins only values of consecutive years"],
}), async ({ page, request }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  const q = r.questions.find((x: any) => x.id === "gr-renters");
  await page.goto(M5("en", "same-question/renters/"));
  const chart = page.locator('[data-m5="chart"]');
  await expect(chart.locator("svg")).toHaveAttribute("aria-label", `${t("en", "m5.question.gr-renters.title")} (${t("en", "m5.unit.percent")})`);
  await expect(chart.locator(".m5-legend li")).toHaveText(q.sources.map((s: any) => t("en", `m5.src.gr-renters.${s.label}`)));
  const values = q.sources.flatMap((s: any) => Object.entries(q.values[s.label]).filter(([, v]) => v != null));
  await expect(chart.locator("circle")).toHaveCount(values.length);
  const consecutive = q.sources.reduce((n: number, s: any) => {
    const ys = Object.keys(q.values[s.label]).filter((y) => q.values[s.label][y] != null).map(Number).sort();
    return n + (ys.some((y, i) => i > 0 && y === ys[i - 1] + 1) ? 1 : 0);
  }, 0);
  await expect(chart.locator("path")).toHaveCount(consecutive);
});

test("the Groups page leads from tenure and household types to their pages in the consistency topic", gwt({
  id: "PW-M5-008",
  given: "the Groups page for Greece, and checks.json with the renters and rent-weight questions and the household-types check",
  when: "it is opened and the household-types link is followed",
  then: ["the tenure section links to the renters and the rent-weight questions", "the household-types section links to the household-types check",
    "following that link opens the check's page"],
}), async ({ page, request, coverage }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  const ids = [...r.checks, ...r.questions].map((x: any) => x.id);
  expect(ids).toEqual(expect.arrayContaining(["gr-renters", "gr-rent-weight", "gr-hbs-household-types"]));
  await page.goto("/en/gr/inflation-by-group/groups/");
  for (const id of ["renters", "rent-weight"]) {
    await expect(page.locator(`#tenure [data-m5-link="${id}"] a`)).toHaveAttribute("href", M5("en", `same-question/${id}/`));
  }
  const types = page.locator('#household [data-m5-link="hbs-household-types"] a');
  await expect(types).toHaveText(`${t("en", "m5.link.hbs-household-types")} →`);
  await coverage.flush();
  await types.click();
  await expect(page).toHaveURL(/\/checks\/hbs-household-types\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(t("en", "m5.check.gr-hbs-household-types.title"));
});

test("a check whose causes aren't all known says what is open, where it is written up, and asks for ideas", gwt({
  id: "PW-M5-009",
  given: "the spending table check, whose differences have no known cause and link to a finding",
  when: "it is opened",
  then: ["a section says how many differences have no known cause yet", "it links to the finding that says what was looked at",
    "it invites ideas by email to the project's support address"],
}), async ({ page, request }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  const c = r.checks.find((x: any) => x.id === "gr-hbs-spending");
  await page.goto(M5("en", "checks/hbs-spending/"));
  const open = page.locator('[data-m5="open"]');
  await expect(open).toContainText(t("en", "m5.open.count", { n: c.differ["not-known"] }));
  await expect(open.locator('a[href$="/checks/hbs-spending/survey-weights/"]')).toHaveCount(1);
  await expect(open.locator('a[href="mailto:support@traceconomics.com"]')).toHaveCount(1);
});

test("the questions page gives each question as a card: its title, a short teaser and a chip per source", gwt({
  id: "PW-M5-010",
  given: "the \"Same question, different sources\" page for Greece and the questions in checks.json",
  when: "it is opened",
  then: ["there is one card per question, each linking to its page with its title and teaser",
    "each card has a chip per kind of source, none repeated, the rent-paid card naming tax returns (AADE) and the national accounts (Eurostat)"],
}), async ({ page, request }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  await page.goto(M5("en", "same-question/"));
  const cards = page.locator('[data-m5="questions"] a.card');
  await expect(cards).toHaveCount(r.questions.length);
  for (const [i, q] of r.questions.entries()) {
    const card = cards.nth(i);
    await expect(card).toHaveAttribute("href", M5("en", `same-question/${q.id.slice(3)}/`));
    await expect(card.locator(".title")).toHaveText(`${t("en", `m5.question.${q.id}.title`)} →`);
    await expect(card.locator(".text")).toHaveText(t("en", `m5.question.${q.id}.teaser`));
    const names = await card.locator(".source-chip").allTextContents();
    expect(names.length).toBeGreaterThan(0);
    expect(new Set(names).size).toBe(names.length);
  }
  const rent = cards.filter({ has: page.locator(".title", { hasText: t("en", "m5.question.gr-rent-paid.title") }) });
  await expect(rent.locator(".source-chip", { hasText: t("en", "m5.chip.tax-aade") })).toHaveCount(1);
  await expect(rent.locator(".source-chip", { hasText: t("en", "m5.chip.na-eurostat") })).toHaveCount(1);
});

test("inside a section, the bar's third row lists the section's pages by short name and marks the one being read", gwt({
  id: "PW-M5-011",
  given: "a check's page, a finding of that check, and a question's page, with the checks and questions in checks.json",
  when: "each is opened",
  then: ["on the check's page the row lists every check in the overview's order, the check being read as plain text marked current and the others as links to their pages",
    "the Checks tab is marked as the current section, not the current page",
    "on the finding's page the same row marks its check as current",
    "on the question's page the row lists every question, that question marked current"],
}), async ({ page, request }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  const order = byStatus(r.checks);
  const strip = page.locator("nav[data-strip]");
  const expectRow = async (items: any[], kind: string, current: string) => {
    await expect(strip.locator("li")).toHaveText(items.map((x) => t("en", `m5.short.${x.id}`)));
    await expect(strip.locator('[aria-current="page"]')).toHaveText(t("en", `m5.short.${current}`));
    for (const x of items.filter((x) => x.id !== current)) {
      await expect(strip.getByRole("link", { name: t("en", `m5.short.${x.id}`), exact: true })).toHaveAttribute("href", M5("en", `${kind}/${x.id.slice(3)}/`));
    }
  };
  await page.goto(M5("en", "checks/cpi-rates-own-index/"));
  await expectRow(order, "checks", "gr-cpi-rates-own-index");
  await expect(page.locator(".topic-nav.sub a", { hasText: t("en", "nav.checks") })).toHaveAttribute("aria-current", "true");
  await page.goto(M5("en", "checks/cpi-rates-own-index/june-2001/"));
  await expect(strip.locator('[aria-current="page"]')).toHaveText(t("en", "m5.short.gr-cpi-rates-own-index"));
  await page.goto(M5("en", "same-question/renters/"));
  await expectRow(r.questions, "same-question", "gr-renters");
});

test("on a phone, the bar's third row opens scrolled to the page being read", gwt({
  id: "PW-M5-012",
  given: ["a phone-sized screen", "a question's page whose row of questions is wider than the screen, the question being read far along it"],
  when: "it is opened",
  then: ["the row is wider than the screen", "the question being read is wholly inside the row's visible part"],
}), async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(M5("en", "same-question/renters/"));
  const list = page.locator("nav[data-strip] ul");
  const box = await list.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth, ...el.getBoundingClientRect().toJSON() }));
  expect(box.scroll).toBeGreaterThan(box.client);
  const item = await list.locator('[aria-current="page"]').boundingBox();
  expect(item!.x).toBeGreaterThanOrEqual(box.left - 1);
  expect(item!.x + item!.width).toBeLessThanOrEqual(box.left + box.client + 1);
});

test("each status's chip has its own colour, and a consistent check's chip carries a tick", gwt({
  id: "PW-M5-013",
  given: "the consistency topic's overview, with consistent, explained and unexplained checks",
  when: "it is opened",
  then: ["chips of different statuses have different background colours",
    "the Consistent chip is drawn with a tick that is not part of its text"],
}), async ({ page }) => {
  await page.goto(M5("en"));
  const chips = await page.locator('[data-m5="checks"] .chip-status').evaluateAll((els) => els.map((el) => ({
    status: [...el.classList].find((c) => c !== "chip-status")!, background: getComputedStyle(el).backgroundColor,
    tick: getComputedStyle(el, "::before").content })));
  const byStatus = new Map(chips.map((c) => [c.status, c.background]));
  expect([...byStatus.keys()]).toEqual(expect.arrayContaining(["agree", "explained"]));
  expect(new Set(byStatus.values()).size).toBe(byStatus.size);
  expect(chips.find((c) => c.status === "agree")!.tick).toContain("✓");
  await expect(page.locator('[data-m5="checks"] .chip-status.agree').first()).toHaveText(t("en", "m5.status.agree"));
});

test("the overview's status buttons show one status's checks at a time", gwt({
  id: "PW-M5-014",
  given: "the consistency topic's overview, with explained, unexplained and consistent checks and none partly explained",
  when: ["the Explained button is pressed", "it is pressed again"],
  then: ["at first every card shows, All is pressed, and there is a button only for each status some check has, with its count",
    "after the first press only the explained cards and the key's explained line show, and the count shown is announced",
    "after the second press every card shows again and All is pressed"],
}), async ({ page, request }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  await page.goto(M5("en"));
  const cards = page.locator('[data-m5="checks"] [data-m5-card]');
  const group = page.getByRole("group", { name: t("en", "m5.filter.label") });
  const present = ORDER.filter((st) => r.checks.some((c: any) => status(c) === st));
  const n = (st: string) => r.checks.filter((c: any) => status(c) === st).length;
  await expect(group.locator("button")).toHaveText([t("en", "m5.filter.count", { label: t("en", "m5.filter.all"), n: r.checks.length }),
    ...present.map((st) => t("en", "m5.filter.count", { label: t("en", `m5.status.${st}`), n: n(st) }))]);
  await expect(group.locator('button[data-filter="all"]')).toHaveAttribute("aria-pressed", "true");
  await expect(cards.filter({ visible: true })).toHaveCount(r.checks.length);
  const explained = group.locator('button[data-filter="explained"]');
  await explained.click();
  await expect(explained).toHaveAttribute("aria-pressed", "true");
  await expect(cards.filter({ visible: true })).toHaveCount(n("explained"));
  for (const c of await cards.filter({ visible: true }).all()) await expect(c).toHaveAttribute("data-status", "explained");
  await expect(page.locator('[data-m5="key"] [data-key]').filter({ visible: true })).toHaveCount(1);
  await expect(page.locator('[data-m5="shown"]')).toHaveText(t("en", "m5.filter.shown", { n: n("explained"), total: r.checks.length }));
  await explained.click();
  await expect(cards.filter({ visible: true })).toHaveCount(r.checks.length);
  await expect(group.locator('button[data-filter="all"]')).toHaveAttribute("aria-pressed", "true");
});

test("the Checks page compares every check in one table, in the overview's order", gwt({
  id: "PW-M5-015",
  given: "the Checks page for Greece and the checks in checks.json",
  when: "it is opened",
  then: ["its table has a row per check in the overview's order", "each row asks the check's question, linking to its page, with its count and status"],
}), async ({ page, request }) => {
  const r = await (await request.get(`${DATA}/checks.json`)).json();
  await page.goto(M5("en", "checks/"));
  const rows = page.locator('[data-m5="check-list"] tbody tr');
  await expect(rows).toHaveCount(r.checks.length);
  for (const [i, c] of byStatus(r.checks).entries()) {
    await expect(rows.nth(i).locator("th a")).toHaveText(t("en", `m5.check.${c.id}.question`));
    await expect(rows.nth(i).locator("th a")).toHaveAttribute("href", M5("en", `checks/${c.id.slice(3)}/`));
    await expect(rows.nth(i)).toContainText(t("en", "m5.count", { agree: num("en", c.agree, 0), compared: num("en", c.compared, 0) }));
    await expect(rows.nth(i).locator(".chip-status")).toHaveText(t("en", `m5.status.${status(c)}`));
  }
});
