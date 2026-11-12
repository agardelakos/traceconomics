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
// The same lines split by layer, for the README's front-end badge (tests/coverage/overview.py): a
// covered line counts for the lowest layer that ran it. Vitest runs twice in a coverage build: the
// unit tests alone (coverage/vitest-unit/raw), then all of them (coverage/vitest/raw). A line in the
// second but not the first is one only the integration tests (those that need the generated data
// files) reach; a line only the browser tests ran is end-to-end.
//
// Writes coverage/report/ (HTML: open index.html), coverage/report/lcov.info, one lcov per layer in
// coverage/layers/ and coverage/summary.json (read by scripts/test-summary.mjs and
// tests/coverage/overview.py).
// Usage: node scripts/coverage.mjs [--strict]
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import { CoverageReport } from "monocart-coverage-reports";
import { FLOOR, sourceFilter, sourcePath, standing } from "./coverage-options.mjs";

const strict = process.argv.includes("--strict");
const INPUTS = ["coverage/vitest/raw", "coverage/ui/raw"];
// The lowest layer first.
const LAYERS = [
  ["unit", "coverage/vitest-unit/raw"],
  ["integration", "coverage/vitest/raw"],
  ["e2e", "coverage/ui/raw"],
];
// Every file here should be loaded by some test.
const SCOPE = ["src/scripts", "src/lib"];

const inputDir = INPUTS.filter((d) => existsSync(d));
for (const d of INPUTS)
  if (!inputDir.includes(d)) console.log(`missing: ${d} (did that test run in a coverage build?)`);
if (!inputDir.length) {
  console.error("no coverage to merge");
  process.exit(1);
}

const report = (name, outputDir, inputDir, reports) =>
  new CoverageReport({
    name,
    outputDir,
    inputDir,
    reports,
    sourceFilter,
    sourcePath,
    logging: "error",
  }).generate();

// Both from the same V8 → Istanbul conversion, so the HTML report and the lcov count lines alike.
await report("Site code coverage", "coverage/report", inputDir, ["html", "lcovonly"]);

/** Each file's lines with code and the covered ones, from an lcov file: "SF:<file>", then "DA:<line>,<hits>". */
function lcov(path) {
  const out = {};
  let current = null;
  for (const line of readFileSync(path, "utf-8").split("\n")) {
    if (line.startsWith("SF:"))
      out[(current = line.slice(3))] = { lines: new Set(), covered: new Set() };
    else if (line.startsWith("DA:") && current) {
      const [n, hits] = line.slice(3).split(",").map(Number);
      out[current].lines.add(n);
      if (hits > 0) out[current].covered.add(n);
    }
  }
  return out;
}

const merged = lcov("coverage/report/lcov.info");
const files = Object.fromEntries(
  Object.entries(merged).map(([f, s]) => [f, { covered: s.covered.size, total: s.lines.size }]),
);

// Each layer's covered lines, converted from that layer's input alone.
const byLayer = [];
for (const [layer, dir] of LAYERS) {
  if (!existsSync(dir)) {
    console.log(`missing: ${dir} (no ${layer} layer in the split)`);
    continue;
  }
  await report(`Site code coverage, ${layer}`, `coverage/layers/${layer}`, [dir], ["lcovonly"]);
  byLayer.push([layer, lcov(`coverage/layers/${layer}/lcov.info`)]);
}
const layerFiles = {};
const problems = [];
for (const [f, s] of Object.entries(merged)) {
  const counts = Object.fromEntries(LAYERS.map(([layer]) => [layer, 0]));
  for (const n of s.covered) {
    const layer = byLayer.find(([, cov]) => cov[f]?.covered.has(n))?.[0];
    if (layer) counts[layer]++;
    else problems.push(`${f}:${n} covered in the merged report but in no layer's`);
  }
  layerFiles[f] = { total: s.lines.size, ...counts };
}

function sources(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = join(dir, e.name);
    if (e.isDirectory()) return sources(p);
    return /\.(ts|mjs)$/.test(e.name) && !/\.(test|d)\.ts$/.test(e.name)
      ? [relative(".", p).replaceAll("\\", "/")]
      : [];
  });
}
const notLoaded = SCOPE.flatMap(sources)
  .filter((f) => !(f in files))
  .sort();

const covered = Object.values(files).reduce((s, f) => s + f.covered, 0);
const total = Object.values(files).reduce((s, f) => s + f.total, 0);
const pct = total ? Math.floor((1000 * covered) / total) / 10 : 0; // rounded down: never claim more
const summary = {
  lines: { covered, total, pct },
  standing: standing(pct),
  inputs: inputDir,
  files: Object.fromEntries(Object.entries(files).sort(([a], [b]) => a.localeCompare(b))),
  notLoaded,
  layers: {
    order: LAYERS.map(([layer]) => layer),
    files: Object.fromEntries(Object.entries(layerFiles).sort(([a], [b]) => a.localeCompare(b))),
    problems,
  },
};
writeFileSync("coverage/summary.json", JSON.stringify(summary, null, 2) + "\n");

console.log(
  `Site code coverage: ${pct}% of lines (${covered} of ${total}), from ${inputDir.join(" and ")}`,
);
for (const [f, s] of Object.entries(summary.files))
  console.log(`  ${(s.total ? ((100 * s.covered) / s.total).toFixed(1) : "-").padStart(5)}%  ${f}`);
if (notLoaded.length) console.log(`Not loaded by any test (not counted): ${notLoaded.join(", ")}`);
const layerTotals = LAYERS.map(
  ([layer]) => `${layer} ${Object.values(layerFiles).reduce((n, f) => n + f[layer], 0)}`,
);
console.log(`Covered lines by layer (lowest first): ${layerTotals.join(", ")}`);
if (problems.length)
  console.log(
    `${problems.length} covered lines in no layer, e.g. ${problems.slice(0, 5).join("; ")}`,
  );
if (strict && notLoaded.length) process.exitCode = 1;
if (strict && pct < FLOOR) {
  console.log(`Below the floor: ${pct}% < ${FLOOR}%`);
  process.exitCode = 1;
}
