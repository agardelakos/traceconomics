// What only a deployed copy has: the host's headers (public/_headers) and the Content Security
// Policy they set. Run against the build's preview address (BASE_URL), in a release's smoke step;
// a local server sends none of these headers, so here the tests skip themselves.
//
// The policy is checked in the browser: every page in the sitemap, and its Greek twin, loads with no
// violation, and so does Explore after it has redrawn for other options (scripts that run only on
// demand could need what the page's first load didn't).
import { existsSync, readFileSync } from "node:fs";
import type { Page } from "@playwright/test";
import { expect, gwt, m1, REMOTE, test } from "./helpers";

const smoke = { tag: "@smoke" };
const SITEMAP = new URL("../../dist/sitemap.xml", import.meta.url);

test.skip(!REMOTE, "needs BASE_URL: a local server sends none of the host's headers");

// Where the page keeps the violations it saw, for the test to read back.
declare global {
  interface Window {
    __csp: string[];
  }
}

/** Every Content Security Policy violation on the page, as the browser reports it. */
async function watch(page: Page): Promise<() => Promise<string[]>> {
  await page.addInitScript(() => {
    window.__csp = [];
    document.addEventListener("securitypolicyviolation", (e) =>
      window.__csp.push(
        `${e.violatedDirective}: ${e.blockedURI || "inline"} (${e.sourceFile}:${e.lineNumber})`,
      ),
    );
  });
  return () => page.evaluate(() => window.__csp);
}

test(
  "pages carry the security headers",
  {
    ...smoke,
    ...gwt({
      id: "PW-HOST-001",
      given: "a deployed copy of the site",
      when: "the English home page is requested",
      then: [
        "its Content Security Policy allows only the site itself by default",
        "it tells browsers not to guess content types (nosniff)",
        "its referrer policy is same-origin",
        "it sets a permissions policy",
      ],
    }),
  },
  async ({ request }) => {
    const headers = (await request.get("/en/")).headers();
    expect(headers["content-security-policy"]).toContain("default-src 'self'");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["referrer-policy"]).toBe("same-origin");
    expect(headers["permissions-policy"]).toBeTruthy();
  },
);

test(
  "data files can be read from other sites",
  {
    ...smoke,
    ...gwt({
      id: "PW-HOST-002",
      given: "a deployed copy of the site",
      when: "a published data file is requested",
      then: ["it is served", "it allows any site to read it (CORS: *)"],
    }),
  },
  async ({ request }) => {
    const response = await request.get("/data/v1/gr/m1/latest/metadata.json");
    expect(response.status()).toBe(200);
    expect(response.headers()["access-control-allow-origin"]).toBe("*");
  },
);

test(
  "no page breaks the Content Security Policy",
  {
    ...smoke,
    ...gwt({
      id: "PW-HOST-003",
      given: ["a deployed copy of the site", "the build's sitemap"],
      when: "every page in the sitemap, and the Greek twin of every English one, is opened in turn",
      then: "the browser reports no Content Security Policy violation on any of them",
    }),
  },
  async ({ page }) => {
    test.skip(!existsSync(SITEMAP), "needs the build's dist/sitemap.xml for the page list");
    test.setTimeout(300_000);
    const paths = [...readFileSync(SITEMAP, "utf-8").matchAll(/<loc>([^<]+)<\/loc>/g)].map(
      (m) => new URL(m[1]).pathname,
    );
    const all = [
      ...paths,
      ...paths.filter((p) => p.startsWith("/en/")).map((p) => p.replace(/^\/en\//, "/el/")),
    ];
    const violations = await watch(page);
    const found: string[] = [];
    for (const path of all) {
      await page.goto(path, { waitUntil: "networkidle" });
      found.push(...(await violations()).map((v) => `${path}: ${v}`));
    }
    expect(found).toEqual([]);
  },
);

test(
  "security.txt is served as plain text",
  {
    ...smoke,
    ...gwt({
      id: "PW-HOST-005",
      given: "a deployed copy of the site",
      when: "/.well-known/security.txt is requested",
      then: ["it is served as plain text", "it is the repository's file, byte for byte"],
    }),
  },
  async ({ request }) => {
    const response = await request.get("/.well-known/security.txt");
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toMatch(/^text\/plain/);
    expect(await response.text()).toBe(
      readFileSync(new URL("../../public/.well-known/security.txt", import.meta.url), "utf-8"),
    );
  },
);

// One page load per test: `watch` starts its list afresh on every new document, so a test that
// opened three addresses in a row would only ever see the last one's violations.
for (const [name, query, drawn] of [
  ["its default view", "", "summary"],
  [
    "other options",
    "?price_source=hicp&weights_timing=U&groups=Q1,Q5,tenure/renter&m=index",
    "summary",
  ],
  ["the parts view", "?groups=Q1,Q5&view=parts", "contrib-title"],
] as const) {
  test(
    `Explore with ${name} draws within the policy`,
    {
      ...smoke,
      ...gwt({
        id: "PW-HOST-004",
        title: "Explore redraws for other options within the policy",
        given: "a deployed copy of the site",
        when: "Explore is opened at its default view, with other options (another price source, weights timing, groups and measure), or with the parts view",
        then: [
          "it is drawn: its summary, or for the parts view the parts title",
          "the browser reports no Content Security Policy violation",
        ],
      }),
    },
    async ({ page }) => {
      const violations = await watch(page);
      await page.goto(`${m1("en", "explore/")}${query}`, { waitUntil: "networkidle" });
      await expect(page.locator(`#explore [data-role="${drawn}"]`)).not.toBeEmpty();
      expect(await violations()).toEqual([]);
    },
  );
}
