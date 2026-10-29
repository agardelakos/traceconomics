// Smoke test: one page of each kind loads, shows its heading and logs no error. It runs on every
// build, before upload (on dist/) and after (on the build's preview address), so a page that builds
// but breaks in the browser never reaches the public site.
import { expect, test, type Page } from "@playwright/test";

const M1 = "/en/gr/inflation-by-group/";
const PAGES = [
  "/en/", "/el/", "/en/countries/", "/en/topics/", "/en/gr/", "/en/inflation-by-group/",
  M1, `${M1}groups/`, `${M1}explore/`, `${M1}calculator/`, `${M1}method/`, `${M1}method/weights-timing/`,
  "/el/gr/inflation-by-group/explore/", "/en/data/", "/en/data/gr/", "/en/glossary/", "/en/glossary/imputed-rent/",
  "/en/about/",
];
// The visit-count beacon is in release builds only; tests block it so they are never counted as visits.
const BEACON = /cloudflareinsights\.com/;
const remote = !!process.env.BASE_URL;

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => {
    // A blocked beacon logs a failed request; that one is ours.
    if (m.type() === "error" && !BEACON.test(m.location().url)) errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(String(e)));
  return errors;
}

test.beforeEach(async ({ context }) => {
  await context.route(BEACON, (route) => route.abort());
});

for (const path of PAGES) {
  test(`${path} loads, shows its heading and logs no error`, async ({ page }) => {
    const errors = collectErrors(page);
    // networkidle: the charts fetch their data after the page loads, and draw when it arrives.
    const response = await page.goto(path, { waitUntil: "networkidle" });
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).not.toHaveText("");
    expect(errors).toEqual([]);
  });
}

test("the root address moves on to a language", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/");
  await expect(page).toHaveURL(/\/(en|el)\/$/);
  expect(errors).toEqual([]);
});

test("a missing address answers 404", async ({ request }) => {
  const response = await request.get("/en/no-such-page/");
  expect(response.status()).toBe(404);
});

// The host's headers exist only on a deployed copy: a local server doesn't apply public/_headers.
test.describe("on the host", () => {
  test.skip(!remote, "needs BASE_URL: a local server sends none of the host's headers");

  test("pages carry the security headers", async ({ request }) => {
    const headers = (await request.get("/en/")).headers();
    expect(headers["content-security-policy"]).toContain("default-src 'self'");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["referrer-policy"]).toBe("same-origin");
    expect(headers["permissions-policy"]).toBeTruthy();
  });

  test("data files can be read from other sites", async ({ request }) => {
    const response = await request.get("/data/v1/gr/m1/latest/metadata.json");
    expect(response.status()).toBe(200);
    expect(response.headers()["access-control-allow-origin"]).toBe("*");
  });
});
