// What the coverage counts, shared by the browser tests (tests/ui/helpers.ts), their teardown and
// the merge (scripts/coverage.mjs), so all three count the same files the same way.
//
// Counted: our own code, as source files (through the coverage build's source maps): src/scripts,
// src/lib, and the <script> blocks of the .astro components, layouts and pages. Not counted: the
// libraries bundled with it (Plot, d3), the tests themselves, data and style files.

/** Below this the build fails (and the badge would be red). */
export const FLOOR = 90;
/** From this up the figure counts as good (green); between the two it is a warning (yellow). */
export const GOOD = 95;

/** The figure's standing: "low" (below FLOOR), "fair" or "good" (GOOD and up). */
export const standing = (pct) => (pct < FLOOR ? "low" : pct < GOOD ? "fair" : "good");

const OURS = /(^|\/)src\/(scripts|lib|components|layouts|pages)\//;

/** A source file we count. */
export const sourceFilter = (path) =>
  !path.includes("node_modules") &&
  OURS.test(path) &&
  !/\.test\.ts$/.test(path) &&
  !/\.(json|css)$/.test(path);

/** "…/site/src/lib/format.ts" → "src/lib/format.ts"; an .astro file's script block gets a readable name. */
export const sourcePath = (path) =>
  path
    .replace(/^.*?(src\/)/, "src/")
    .replace(/\.astro\??(?:astro)?[?&]type=script&index=(\d+)&lang\.ts$/, ".astro (script $1)");

/**
 * The browser tests' raw coverage: only the site's own scripts, never a third-party one.
 * @type {import("monocart-coverage-reports").CoverageReportOptions}
 */
export const ui = {
  name: "browser tests",
  outputDir: "coverage/ui",
  reports: ["raw"],
  logging: "error",
  entryFilter: (entry) => entry.url.includes("/_astro/"),
  sourceFilter,
  sourcePath,
};

/** Where the browser tests write each test's own raw coverage for the code map (TRACECONOMICS_CODE_MAP=on). */
export const CODE_MAP_DIR = "coverage/ui-pertest";

/**
 * The Vitest files that need the generated data files: the integration layer. The rest are unit
 * tests. The same two files are left out of `npm run check:code` and of CI's unit-only run;
 * tests/test_code_map.py checks that the three lists agree.
 */
export const VITEST_INTEGRATION = ["src/lib/engine/parity.test.ts", "src/lib/data-files.test.ts"];
