// Vitest's settings. The defaults hold (files named *.test.ts); this file only adds coverage, and
// only when TRACECONOMICS_COVERAGE=on (CI). Coverage goes through the same converter as the
// browser tests' (monocart), as raw V8 data, so `scripts/coverage.mjs` can merge the two into one
// count: a line covered by either kind of test counts once.
import { defineConfig } from "vitest/config";

const coverage = process.env.TRACECONOMICS_COVERAGE === "on";
// TRACECONOMICS_COVERAGE_DIR: CI's second run, of the unit tests alone (scripts/coverage.mjs).
const coverageDir = process.env.TRACECONOMICS_COVERAGE_DIR ?? "coverage/vitest";

export default defineConfig({
  test: {
    // A JSON report beside the console's, on every run: the test catalog reads each test's case
    // from it (`meta`, which Vitest's own listing leaves out), and the run history its results.
    reporters: ["default", "json"],
    outputFile: { json: "test-reports/vitest.json" },
    includeTaskLocation: true,
    coverage: {
      enabled: coverage,
      include: ["src/**"],
      // Vitest empties this folder when a coverage run starts; its default (all of coverage/) would
      // delete the other run's data and the browser tests'.
      reportsDirectory: coverageDir,
      provider: "custom",
      customProviderModule: "vitest-monocart-coverage",
      // @ts-expect-error: the monocart provider's own option, unknown to Vitest's types.
      coverageReportOptions: {
        name: "vitest",
        outputDir: coverageDir,
        reports: ["raw"],
        logging: "error",
      },
    },
  },
});
