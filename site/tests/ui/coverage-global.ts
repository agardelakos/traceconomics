// Before the browser tests: clear coverage left by an earlier run. After them (the function this
// returns): write the run's coverage as raw V8 data, for scripts/coverage.mjs to merge with Vitest's.
// Only in a coverage build (TRACECONOMICS_COVERAGE=on) on dist/, never against a deployed copy.
import { rmSync } from "node:fs";
import { CoverageReport } from "monocart-coverage-reports";
import { ui } from "../../scripts/coverage-options.mjs";

export default function setup() {
  if (process.env.TRACECONOMICS_COVERAGE !== "on" || process.env.BASE_URL) return;
  rmSync(ui.outputDir!, { recursive: true, force: true });
  return async () => {
    await new CoverageReport(ui).generate();
  };
}
