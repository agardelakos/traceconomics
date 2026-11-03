// What only a deployed copy has: the host's headers (public/_headers) and the Content Security
// Policy they set. Run against the build's preview address (BASE_URL), in a release's smoke step;
// a local server sends none of these headers, so here the tests skip themselves.
//
// The policy is checked in the browser: every page in the sitemap, and its Greek twin, loads with no
// violation, and so does Explore after it has redrawn for other options (scripts that run only on
// demand could need what the page's first load didn't).
import { existsSync, readFileSync } from "node:fs";
import type { Page } from "@playwright/test";
import { expect, m1, REMOTE, test } from "./helpers";

const smoke = { tag: "@smoke" };
const SITEMAP = new URL("../../dist/sitemap.xml", import.meta.url);

test.skip(!REMOTE, "needs BASE_URL: a local server sends none of the host's headers");

/** Every Content Security Policy violation on the page, as the browser reports it. */
async function watch(page: Page): Promise<() => Promise<string[]>> {
  await page.addInitScript(() => {
    (window as any).__csp = [];
    document.addEventListener("securitypolicyviolation", (e) =>
      (window as any).__csp.push(`${e.violatedDirective}: ${e.blockedURI || "inline"} (${e.sourceFile}:${e.lineNumber})`));
  });
  return () => page.evaluate(() => (window as any).__csp as string[]);
}

test("pages carry the security headers", smoke, async ({ request }) => {
  const headers = (await request.get("/en/")).headers();
  expect(headers["content-security-policy"]).toContain("default-src 'self'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBe("same-origin");
  expect(headers["permissions-policy"]).toBeTruthy();
});

test("data files can be read from other sites", smoke, async ({ request }) => {
  const response = await request.get("/data/v1/gr/m1/latest/metadata.json");
  expect(response.status()).toBe(200);
  expect(response.headers()["access-control-allow-origin"]).toBe("*");
});

test("no page breaks the Content Security Policy", smoke, async ({ page }) => {
  test.skip(!existsSync(SITEMAP), "needs the build's dist/sitemap.xml for the page list");
  test.setTimeout(300_000);
  const paths = [...readFileSync(SITEMAP, "utf-8").matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => new URL(m[1]).pathname);
  const all = [...paths, ...paths.filter((p) => p.startsWith("/en/")).map((p) => p.replace(/^\/en\//, "/el/"))];
  const violations = await watch(page);
  const found: string[] = [];
  for (const path of all) {
    await page.goto(path, { waitUntil: "networkidle" });
    found.push(...(await violations()).map((v) => `${path}: ${v}`));
  }
  expect(found).toEqual([]);
});

test("Explore redraws for other options within the policy", smoke, async ({ page }) => {
  const violations = await watch(page);
  await page.goto(m1("en", "explore/"), { waitUntil: "networkidle" });
  await page.goto(`${m1("en", "explore/")}?price_source=hicp&weights_timing=U&groups=Q1,Q5,tenure/renter&m=index`, { waitUntil: "networkidle" });
  await page.goto(`${m1("en", "explore/")}?groups=Q1,Q5&view=parts`, { waitUntil: "networkidle" });
  await expect(page.locator('#explore [data-role="contrib-title"]')).not.toBeEmpty();
  expect(await violations()).toEqual([]);
});
