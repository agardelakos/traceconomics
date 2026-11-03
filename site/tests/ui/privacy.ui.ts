// The privacy promises the pages make: nothing a reader types leaves the device (no request carries
// it), nothing is stored but the theme choice, no cookies, and no requests to other sites (release
// builds add one, the visit counter, which the tests block).
import type { Page, Request } from "@playwright/test";
import { expect, m1, t, test } from "./helpers";

// Amounts unlikely to appear anywhere by chance.
const INCOME = "23457";
const EUROS = "1379";

function record(page: Page): Request[] {
  const requests: Request[] = [];
  page.on("request", (r) => requests.push(r));
  return requests;
}
const carries = (r: Request, text: string) => r.url().includes(text) || (r.postData() ?? "").includes(text) ||
  Object.values(r.headers()).some((v) => v.includes(text));

async function storage(page: Page) {
  return page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage) }));
}

test("the group finder sends nothing it is told, and stores nothing", async ({ page, context, coverage }) => {
  const requests = record(page);
  await page.goto(m1("en", "groups/"));
  const f = page.locator("#find");
  await f.getByLabel(t("en", "find.income")).fill(INCOME);
  await f.getByLabel(t("en", "find.home.renter")).check();
  await expect(f.locator('[data-find="income-value"]')).not.toBeEmpty();
  // Follow a link it offers too: the next page's request must not carry the income either.
  await coverage.flush();
  await f.locator('[data-find="starts"] a').first().click();
  await page.waitForLoadState("networkidle");
  expect(requests.filter((r) => carries(r, INCOME)).map((r) => r.url())).toEqual([]);
  expect(await storage(page)).toEqual({ local: [], session: [] });
  expect(await context.cookies()).toEqual([]);
});

test("the calculator sends nothing it is told, and stores nothing", async ({ page, context }) => {
  const requests = record(page);
  await page.goto(m1("en", "calculator/"));
  await expect(page.locator('#calculator [data-role="result"]')).toBeVisible();
  await page.getByRole("button", { name: t("en", "calc.mode.euros") }).click();
  await page.locator("#calculator .euro-row input").first().fill(EUROS);
  await expect(page.locator('#calculator [data-role="euros-empty"]')).toBeHidden();
  await page.getByRole("button", { name: t("en", "calc.mode.shares") }).click();
  await page.locator('#calculator input[type="range"]').first().fill("33");
  await page.waitForLoadState("networkidle");
  expect(requests.filter((r) => carries(r, EUROS)).map((r) => r.url())).toEqual([]);
  expect(new URL(page.url()).search).toBe("");            // the address holds no spending either
  expect(await storage(page)).toEqual({ local: [], session: [] });
  expect(await context.cookies()).toEqual([]);
});

test("the theme is the only thing kept, under one key", async ({ page }) => {
  await page.goto("/en/");
  await page.getByRole("button", { name: t("en", "settings.label") }).click();
  await page.getByRole("radio", { name: t("en", "theme.dark") }).check();
  await page.goto(m1("en", "explore/?groups=Q1,Q2"));
  await expect(page.locator('#explore [data-role="summary"]')).not.toBeEmpty();
  expect(await storage(page)).toEqual({ local: ["theme"], session: [] });
});

test("pages ask nothing of other sites", async ({ page, baseURL }) => {
  const requests = record(page);
  for (const path of ["/en/", m1("en"), m1("en", "explore/"), m1("en", "calculator/"), m1("en", "groups/"), "/en/data/gr/", "/en/glossary/"]) {
    await page.goto(path, { waitUntil: "networkidle" });
  }
  const origin = new URL(baseURL!).origin;
  const elsewhere = requests.map((r) => r.url()).filter((u) => !u.startsWith("data:") && new URL(u).origin !== origin);
  // The visit counter is in release builds only and blocked here; anything else is a broken promise.
  expect(elsewhere.filter((u) => !/cloudflareinsights\.com/.test(u))).toEqual([]);
});
