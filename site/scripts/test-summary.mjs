// A Markdown summary of the browser tests, from Playwright's results file
// (test-reports/playwright.json): passed, failed and skipped, and each failure's name and first
// error line; then the coverage count, if there is one (coverage/summary.json). On GitHub it goes
// on the run's page ($GITHUB_STEP_SUMMARY), below the report Vitest writes there itself; elsewhere
// it is printed. A missing file is reported, not skipped: a test
// that never ran (an earlier step failed) is worth seeing.
// Usage: node scripts/test-summary.mjs [folder]   (default test-reports)
import { appendFileSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { FLOOR, GOOD } from "./coverage-options.mjs";

const folder = process.argv[2] ?? "test-reports";
// eslint-disable-next-line no-control-regex -- matches the terminal's colour codes (ESC [ … m) to strip them
const ANSI = /\u001b\[[0-9;]*m/g;

function firstLine(text) {
  const line =
    String(text ?? "")
      .replace(ANSI, "")
      .split("\n")
      .map((l) => l.trim())
      .find(Boolean) ?? "";
  return (line.length > 200 ? line.slice(0, 199) + "…" : line).replaceAll("|", "\\|");
}

function read(name) {
  const path = join(folder, name);
  return existsSync(path) ? JSON.parse(readFileSync(path, "utf-8")) : null;
}

function playwright(r) {
  const failures = [];
  const walk = (suite, path) => {
    for (const spec of suite.specs ?? []) {
      for (const t of spec.tests) {
        if (t.status === "unexpected" || t.status === "flaky") {
          const error = t.results.find((x) => x.error)?.error?.message;
          failures.push([[...path, spec.title].filter(Boolean).join(" › "), error]);
        }
      }
    }
    for (const s of suite.suites ?? []) walk(s, [...path, s.title]);
  };
  for (const s of r.suites ?? []) walk(s, [s.title]); // the top level is the test file
  // Errors outside any test (the server didn't start, a file didn't load).
  for (const e of r.errors ?? []) failures.push(["(outside the tests)", e.message]);
  // Per test file: what each area of the site got.
  const files = [];
  const count = (suite, tally) => {
    for (const spec of suite.specs ?? [])
      for (const t of spec.tests) {
        if (t.status === "expected") tally.passed++;
        else if (t.status === "skipped") tally.skipped++;
        else tally.failed++;
      }
    for (const s of suite.suites ?? []) count(s, tally);
    return tally;
  };
  for (const s of r.suites ?? [])
    files.push([s.title, count(s, { passed: 0, failed: 0, skipped: 0 })]);
  const st = r.stats ?? {};
  return {
    passed: st.expected ?? 0,
    failed: (st.unexpected ?? 0) + (st.flaky ?? 0),
    skipped: st.skipped ?? 0,
    failures,
    files,
  };
}

const data = read("playwright.json");
const lines = ["## Browser tests (Playwright)", ""];
const failed = [];
if (!data) {
  lines.push("No results: it didn't run (an earlier step failed).");
} else {
  const s = playwright(data);
  lines.push(
    "| Passed | Failed | Skipped |",
    "|---:|---:|---:|",
    `| ${s.passed} | ${s.failed ? `**${s.failed}**` : 0} | ${s.skipped} |`,
  );
  if (s.files.length > 1) {
    lines.push(
      "",
      "<details><summary>By test file</summary>",
      "",
      "| File | Passed | Failed | Skipped |",
      "|---|---:|---:|---:|",
      ...s.files.map(
        ([f, c]) => `| ${f} | ${c.passed} | ${c.failed ? `**${c.failed}**` : 0} | ${c.skipped} |`,
      ),
      "",
      "</details>",
    );
  }
  failed.push(...s.failures.map(([title, error]) => `- ${firstLine(title)}: ${firstLine(error)}`));
}
if (failed.length) lines.push("", "### Failures", "", ...failed);
if (data) {
  lines.push(
    "",
    "Every test, with its result (and for a failure its screenshot, console errors and trace), is in the report attached to this run as `ui-test-report` (kept 7 days): download it, unzip, open `index.html`.",
  );
}
// The coverage count, when scripts/coverage.mjs ran (CI's coverage build).
const coverage = existsSync("coverage/summary.json")
  ? JSON.parse(readFileSync("coverage/summary.json", "utf-8"))
  : null;
if (coverage) {
  const { pct, covered, total } = coverage.lines;
  const mark = {
    good: "🟢 good",
    fair: `🟡 below the ${GOOD}% mark`,
    low: `🔴 below the ${FLOOR}% floor: the build fails`,
  }[coverage.standing];
  lines.push(
    "",
    "## Site code coverage (Vitest and the browser tests)",
    "",
    `**${pct}%** (${mark}) of lines with code ran in at least one test (${covered} of ${total}). The report is attached to this run as \`site-coverage\`.`,
  );
  if (coverage.notLoaded.length) {
    lines.push(
      "",
      `Not loaded by any test, so not counted (${coverage.notLoaded.length}): ${coverage.notLoaded.map((f) => `\`${f}\``).join(", ")}`,
    );
  }
}
const text = lines.join("\n") + "\n";
if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, text);
else process.stdout.write(text);
