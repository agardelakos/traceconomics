// One coverage count for the site's own code, from both kinds of test: Vitest (coverage/vitest/raw)
// and the browser tests (coverage/ui/raw), each written in a coverage build (TRACECONOMICS_COVERAGE=on).
//
// The figure is lines: of the lines that hold code, the share that ran at least once in either kind
// of test (as an lcov file counts them). A line run by both counts once.
//
// Files that no test loads have no lines to count, so they would quietly drop out of the figure.
// They are listed instead ("not loaded by any test"). With --strict that list must be empty and
// the figure at least FLOOR (coverage-options.mjs).
//
// Writes coverage/report/ (HTML: open index.html), coverage/report/lcov.info and coverage/summary.json
// (read by scripts/test-summary.mjs and scripts/badge.mjs).
// Usage: node scripts/coverage.mjs [--strict]
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import { CoverageReport } from "monocart-coverage-reports";
import { FLOOR, sourceFilter, sourcePath, standing } from "./coverage-options.mjs";

const strict = process.argv.includes("--strict");
const INPUTS = ["coverage/vitest/raw", "coverage/ui/raw"];
// Every file here should be loaded by some test.
const SCOPE = ["src/scripts", "src/lib"];

const inputDir = INPUTS.filter((d) => existsSync(d));
for (const d of INPUTS) if (!inputDir.includes(d)) console.log(`missing: ${d} (did that test run in a coverage build?)`);
if (!inputDir.length) {
  console.error("no coverage to merge");
  process.exit(1);
}

await new CoverageReport({
  name: "Site code coverage",
  outputDir: "coverage/report",
  inputDir,
  // Both from the same V8 → Istanbul conversion, so the HTML report and the lcov count lines alike.
  reports: ["html", "lcovonly"],
  sourceFilter,
  sourcePath,
  logging: "error",
}).generate();

// Lines per file, from the lcov file: "SF:<file>", then "DA:<line>,<hits>" for each line with code.
const files = {};
let current = null;
for (const line of readFileSync("coverage/report/lcov.info", "utf-8").split("\n")) {
  if (line.startsWith("SF:")) files[(current = line.slice(3))] = { covered: 0, total: 0 };
  else if (line.startsWith("DA:") && current) {
    const hits = Number(line.split(",")[1]);
    files[current].total++;
    if (hits > 0) files[current].covered++;
  }
}

function sources(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = join(dir, e.name);
    if (e.isDirectory()) return sources(p);
    return /\.(ts|mjs)$/.test(e.name) && !/\.(test|d)\.ts$/.test(e.name) ? [relative(".", p).replaceAll("\\", "/")] : [];
  });
}
const notLoaded = SCOPE.flatMap(sources).filter((f) => !(f in files)).sort();

const covered = Object.values(files).reduce((s, f) => s + f.covered, 0);
const total = Object.values(files).reduce((s, f) => s + f.total, 0);
const pct = total ? Math.floor((1000 * covered) / total) / 10 : 0;     // rounded down: never claim more
const summary = {
  lines: { covered, total, pct },
  standing: standing(pct),
  inputs: inputDir,
  files: Object.fromEntries(Object.entries(files).sort(([a], [b]) => a.localeCompare(b))),
  notLoaded,
};
writeFileSync("coverage/summary.json", JSON.stringify(summary, null, 2) + "\n");

console.log(`Site code coverage: ${pct}% of lines (${covered} of ${total}), from ${inputDir.join(" and ")}`);
for (const [f, s] of Object.entries(summary.files)) console.log(`  ${(s.total ? (100 * s.covered / s.total).toFixed(1) : "-").padStart(5)}%  ${f}`);
if (notLoaded.length) console.log(`Not loaded by any test (not counted): ${notLoaded.join(", ")}`);
if (strict && notLoaded.length) process.exitCode = 1;
if (strict && pct < FLOOR) {
  console.log(`Below the floor: ${pct}% < ${FLOOR}%`);
  process.exitCode = 1;
}
