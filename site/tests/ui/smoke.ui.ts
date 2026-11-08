// Smoke test: one page of each kind loads and shows its heading (and, as in every test, logs no
// error). It runs on every build, before upload (on dist/) and after (on the build's preview
// address, with the host's own checks in host.ui.ts: the tests tagged @smoke), so a page that
// builds but breaks in the browser never reaches the public site.
import { expect, gwt, m1, test } from "./helpers";

const M1 = m1("en");
const PAGES = [
  "/en/", "/el/", "/en/countries/", "/en/topics/", "/en/gr/", "/en/inflation-by-group/",
  M1, `${M1}groups/`, `${M1}explore/`, `${M1}calculator/`, `${M1}method/`, `${M1}method/weights-timing/`,
  m1("el", "explore/"), "/en/data/", "/en/data/gr/", "/en/glossary/", "/en/glossary/imputed-rent/",
  "/en/about/", "/en/official-figures-consistency/", "/en/gr/official-figures-consistency/",
  "/en/gr/official-figures-consistency/checks/", "/en/gr/official-figures-consistency/checks/cpi-rates-own-index/",
  "/en/gr/official-figures-consistency/checks/cpi-rates-own-index/june-2001/",
  "/en/gr/official-figures-consistency/same-question/", "/en/gr/official-figures-consistency/method/",
];
const smoke = { tag: "@smoke" };

for (const path of PAGES) {
  test(`${path} loads, shows its heading and logs no error`, { ...smoke, ...gwt({
    id: "PW-SMOKE-001",
    title: "each main page loads, shows its heading and logs no error",
    given: "a page of one of the site's kinds",
    when: "it is opened and has finished loading its data",
    then: ["it answers with success (200)", "its main heading is shown and is not empty", "the browser logs no error"],
  }) }, async ({ page }) => {
    // networkidle: the charts fetch their data after the page loads, and draw when it arrives.
    const response = await page.goto(path, { waitUntil: "networkidle" });
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).not.toHaveText("");
  });
}

test("the root address moves on to a language", { ...smoke, ...gwt({
  id: "PW-SMOKE-002",
  given: "the site's root address, with no language in it",
  when: "it is opened",
  then: "the visitor ends up on the English or the Greek home page",
}) }, async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/(en|el)\/$/);
});

test("a missing address answers 404", { ...smoke, ...gwt({
  id: "PW-SMOKE-003",
  given: "an address where the site has no page",
  when: "it is requested",
  then: "the site answers 404 (not found)",
}) }, async ({ request }) => {
  const response = await request.get("/en/no-such-page/");
  expect(response.status()).toBe(404);
});
