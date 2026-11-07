// What every browser test shares. Import `test` and `expect` from here, not from @playwright/test:
//
//  - the visit-count beacon is blocked (release builds carry it; a test must never count as a visit);
//  - any console error or uncaught exception fails the test, with the errors attached to the report;
//  - with TRACECONOMICS_COVERAGE=on (CI's coverage build), the lines our scripts run are recorded.
//
// Expected values come from the site's own files and texts, never typed in: `t()` is the site's
// own text lookup (a missing key throws), `json()` reads a published data file.
import { readFileSync } from "node:fs";
import { test as base, expect, type APIRequestContext, type Page } from "@playwright/test";
import { CoverageReport } from "monocart-coverage-reports";
import { ui as coverageOptions } from "../../scripts/coverage-options.mjs";
import { fill, type Lang } from "../../src/lib/format";

export { expect };
export { month, num, type Lang } from "../../src/lib/format";

// The language files, read as the site's src/lib/i18n.ts reads them (Node won't import JSON from
// that module without an import attribute, so the lookup is repeated here, just as strict).
const strings = (name: string) => JSON.parse(readFileSync(new URL(`../../src/i18n/${name}.json`, import.meta.url), "utf-8"));
const STRINGS: Record<Lang, Record<string, string>> = { el: strings("el"), en: strings("en") };
/**
 * A test's case: its stable ID and its Given/When/Then, as Playwright annotations, so the case is
 * written on the test it describes. The test catalog reads them from `playwright test --list`, and
 * they show in the HTML report. Pass it as the test's details: `test(title, gwt({ … }), body)`, or
 * spread it next to other details: `{ tag: "@smoke", ...gwt({ … }) }`. A loop that makes the same
 * test per language passes the same case: one ID, the languages are its examples. Give the case a
 * `title` when the test's own title is the loop's value (a page's address): the case needs a name.
 */
export function gwt(c: { id: string; title?: string; given: string | string[]; when: string | string[]; then: string | string[] }) {
  const steps = (type: string, v: string | string[]) => [v].flat().map((description) => ({ type, description }));
  const title = c.title ? [{ type: "title", description: c.title }] : [];
  return { annotation: [{ type: "id", description: c.id }, ...title, ...steps("given", c.given), ...steps("when", c.when), ...steps("then", c.then)] };
}

export const LANGS: Lang[] = ["el", "en"];
/** The languages offered to readers; the others are built but not linked. */
export const OFFERED: Lang[] = strings("languages").offered;

/** A text in a site language, as the site shows it. A missing key is an error. */
export function t(lang: Lang, key: string, vars: Record<string, string | number> = {}): string {
  const text = STRINGS[lang][key];
  if (text === undefined) throw new Error(`missing text "${key}" for ${lang}`);
  return fill(text, vars);
}

export const BEACON = /cloudflareinsights\.com/;
/** Testing a deployed copy (BASE_URL), as a release's `smoke` step does, rather than dist/. */
export const REMOTE = !!process.env.BASE_URL;
const COVERAGE = process.env.TRACECONOMICS_COVERAGE === "on" && !REMOTE;

/** Module 1's pages for a language: m1("en", "explore/") → "/en/gr/inflation-by-group/explore/". */
export const m1 = (lang: string, rest = "") => `/${lang}/gr/inflation-by-group/${rest}`;

/** A published data file, parsed. */
export async function json<T = any>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(path);
  expect(response.status(), path).toBe(200);
  return response.json();
}

interface Fixtures {
  /** Console errors that are expected in this test (rare: say why where it's set). */
  allowErrors: RegExp[];
  errors: string[];
  /**
   * Chromium forgets a page's coverage when the next page loads. `page.goto` and `page.reload`
   * keep it themselves; call `coverage.flush()` before any other action that loads a new page
   * (a click on a link, a form). Without coverage it does nothing.
   */
  coverage: { flush(): Promise<void> };
}

export const test = base.extend<Fixtures>({
  allowErrors: [[], { option: true }],

  context: async ({ context }, use) => {
    await context.route(BEACON, (route) => route.abort());
    await use(context);
  },

  errors: [async ({ page, allowErrors }, use, info) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      // A blocked beacon logs a failed request; that one is ours.
      if (m.type() === "error" && !BEACON.test(m.location().url)) errors.push(m.text());
    });
    page.on("pageerror", (e) => errors.push(String(e)));
    await use(errors);
    const unexpected = errors.filter((e) => !allowErrors.some((re) => re.test(e)));
    // In full in the report, next to the screenshot (the assertion shows only a diff).
    if (unexpected.length) await info.attach("console errors", { body: unexpected.join("\n\n"), contentType: "text/plain" });
    expect(unexpected, "console errors").toEqual([]);
  }, { auto: true }],

  coverage: [async ({ page, javaScriptEnabled }, use) => {
    // With scripts off there is nothing to measure, and Chromium refuses to start the coverage.
    if (!COVERAGE || !javaScriptEnabled) {
      await use({ flush: async () => {} });
      return;
    }
    const entries: any[] = [];
    let running = false;
    const stop = async () => {
      if (!running) return;
      running = false;
      entries.push(...(await page.coverage.stopJSCoverage()));
    };
    const flush = async () => {
      await stop();
      await page.coverage.startJSCoverage({ resetOnNavigation: false });
      running = true;
    };
    const goto = page.goto.bind(page);
    const reload = page.reload.bind(page);
    page.goto = (async (...args: Parameters<Page["goto"]>) => { await flush(); return goto(...args); }) as Page["goto"];
    page.reload = (async (...args: Parameters<Page["reload"]>) => { await flush(); return reload(...args); }) as Page["reload"];
    await use({ flush });
    await stop().catch(() => {});        // the test may have closed the page
    if (entries.length) await new CoverageReport(coverageOptions).add(entries);
  }, { auto: true }],
});
