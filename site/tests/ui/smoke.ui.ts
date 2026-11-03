// Smoke test: one page of each kind loads and shows its heading (and, as in every test, logs no
// error). It runs on every build, before upload (on dist/) and after (on the build's preview
// address, with the host's own checks in host.ui.ts: the tests tagged @smoke), so a page that
// builds but breaks in the browser never reaches the public site.
import { expect, m1, test } from "./helpers";

const M1 = m1("en");
const PAGES = [
  "/en/", "/el/", "/en/countries/", "/en/topics/", "/en/gr/", "/en/inflation-by-group/",
  M1, `${M1}groups/`, `${M1}explore/`, `${M1}calculator/`, `${M1}method/`, `${M1}method/weights-timing/`,
  m1("el", "explore/"), "/en/data/", "/en/data/gr/", "/en/glossary/", "/en/glossary/imputed-rent/",
  "/en/about/",
];
const smoke = { tag: "@smoke" };

for (const path of PAGES) {
  test(`${path} loads, shows its heading and logs no error`, smoke, async ({ page }) => {
    // networkidle: the charts fetch their data after the page loads, and draw when it arrives.
    const response = await page.goto(path, { waitUntil: "networkidle" });
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).not.toHaveText("");
  });
}

test("the root address moves on to a language", smoke, async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/(en|el)\/$/);
});

test("a missing address answers 404", smoke, async ({ request }) => {
  const response = await request.get("/en/no-such-page/");
  expect(response.status()).toBe(404);
});
