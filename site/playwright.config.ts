// Browser tests of the built site (`npm run test:ui`), with Playwright's own Chromium.
//
// Two ways to run, the same tests:
//  - against `dist/` on a local server (the default): build first; this is how CI and a release's
//    `ui-test` step run them;
//  - against a deployed address (`BASE_URL=https://…`): how a release's `smoke` step checks its
//    preview, with the host's real headers, which only a deployed copy has.
//
// No retries: a test that passes only on a second try is a bug to fix, and a release is held back
// until it is. A failing test keeps a screenshot and a trace (a step-by-step replay with the network
// and the console). `UI_OUTPUT`, `UI_REPORT` and `UI_JSON` put the traces, the HTML report and the
// results file where a release keeps them; the results file feeds CI's summary and the release email.
import { defineConfig, devices } from "@playwright/test";

const remote = process.env.BASE_URL;
const local = "http://127.0.0.1:4322";

export default defineConfig({
  testDir: "tests/ui",
  // Not *.test.ts or *.spec.ts: Vitest runs those.
  testMatch: "**/*.ui.ts",
  retries: 0,
  forbidOnly: true,
  outputDir: process.env.UI_OUTPUT ?? "test-results",
  reporter: [
    ["list"],
    ["html", { outputFolder: process.env.UI_REPORT ?? "playwright-report", open: "never" }],
    // Outside the two folders above: Playwright empties those at the start of a run.
    ["json", { outputFile: process.env.UI_JSON ?? "test-reports/playwright.json" }],
    // On GitHub, failures are also marked on the run's page and in a pull request's diff.
    ...(process.env.GITHUB_ACTIONS === "true" ? [["github"] as ["github"]] : []),
  ],
  use: {
    baseURL: remote ?? local,
    timezoneId: "Europe/Athens",
    locale: "en-GB",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // --ignore-lock keeps the server in the foreground, where Playwright can stop it: Astro otherwise
  // moves it to the background when it thinks an AI coding agent started it.
  webServer: remote
    ? undefined
    : { command: "npx astro preview --host 127.0.0.1 --port 4322 --ignore-lock", url: `${local}/en/`, reuseExistingServer: false },
});
