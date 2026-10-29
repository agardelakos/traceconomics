// A Markdown summary of the browser smoke test, from Playwright's results file
// (test-reports/playwright.json): passed, failed and skipped, and each failure's name and first
// error line. On GitHub it goes on the run's page ($GITHUB_STEP_SUMMARY), below the report Vitest
// writes there itself; elsewhere it is printed. A missing file is reported, not skipped: a test
// that never ran (an earlier step failed) is worth seeing.
// Usage: node scripts/test-summary.mjs [folder]   (default test-reports)
import { appendFileSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const folder = process.argv[2] ?? "test-reports";
const ANSI = /\u001b\[[0-9;]*m/g;

function firstLine(text) {
  const line = String(text ?? "").replace(ANSI, "").split("\n").map((l) => l.trim()).find(Boolean) ?? "";
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
  for (const s of r.suites ?? []) walk(s, [s.title]);   // the top level is the test file
  // Errors outside any test (the server didn't start, a file didn't load).
  for (const e of r.errors ?? []) failures.push(["(outside the tests)", e.message]);
  const st = r.stats ?? {};
  return { passed: st.expected ?? 0, failed: (st.unexpected ?? 0) + (st.flaky ?? 0), skipped: st.skipped ?? 0, failures };
}

const data = read("playwright.json");
const lines = ["## Browser smoke test (Playwright)", ""];
const failed = [];
if (!data) {
  lines.push("No results: it didn't run (an earlier step failed).");
} else {
  const s = playwright(data);
  lines.push("| Passed | Failed | Skipped |", "|---:|---:|---:|", `| ${s.passed} | ${s.failed ? `**${s.failed}**` : 0} | ${s.skipped} |`);
  failed.push(...s.failures.map(([title, error]) => `- ${firstLine(title)}: ${firstLine(error)}`));
}
if (failed.length) {
  lines.push("", "### Failures", "", ...failed, "",
    "The browser test's report (screenshots, console errors, traces) is attached to this run as `ui-test-report` (kept 7 days): download it and open `index.html`.");
}
const text = lines.join("\n") + "\n";
if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, text);
else process.stdout.write(text);
