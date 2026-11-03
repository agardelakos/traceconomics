"""Runs the site's two browser suites, Playwright (site/tests/ui) and Selenium (tests/selenium), several
times each on the same build and the same number of workers, and writes a Markdown comparison:
wall time, tests run, failures, flaky tests (failed in some runs, passed in others), the slowest
files, and lines of test code.

The Playwright suite is run as a black box through its own npm script and JSON reporter, with its
own `--fully-parallel` flag: pytest-xdist spreads single tests over the workers, and the flag makes
Playwright do the same, so the times compare like for like. (Without it, as its config stands,
Playwright runs the tests of one file one after another in one worker.) `--per-file` adds a column
for Playwright run that way too.

    python -I tests/selenium/compare.py --runs 5 [--workers 8] [--per-file] [--out comparison.md]

Build the site first (`npm run build` in site/). On GitHub its output also goes on the run's page.
Standard library only.
"""

import argparse
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
# `python -I` leaves the script's own folder off the import path; report.py sits next to this file.
sys.path.insert(0, str(HERE))
import report  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
NOT_TESTS = {"compare.py", "report.py"}       # tools, not test code: left out of the line count


def run_playwright(workers: int, out: Path, fully_parallel: bool = False) -> tuple[float, report.Results]:
    path = out / "playwright.json"
    env = {**os.environ, "PLAYWRIGHT_JSON_OUTPUT_FILE": str(path)}
    env.pop("TRACECONOMICS_COVERAGE", None)    # a plain build, as the Selenium suite gets
    npm = shutil.which("npm") or "npm"
    args = [npm, "run", "test:ui", "--", "--reporter=json", f"--workers={workers}"] + (["--fully-parallel"] if fully_parallel else [])
    start = time.monotonic()
    subprocess.run(args, cwd=SITE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return time.monotonic() - start, report.playwright(path) or report.Results()


def run_selenium(workers: int, out: Path) -> tuple[float, report.Results]:
    path = out / "junit.xml"
    start = time.monotonic()
    subprocess.run([sys.executable, "-I", "-m", "pytest", "tests/selenium", "--selenium", "-n", str(workers),
                    "-q", "-p", "no:cacheprovider", f"--junitxml={path}"], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return time.monotonic() - start, report.selenium(path) or report.Results()


def lines_of_code(paths: list[Path]) -> tuple[int, int]:
    """Files and non-blank lines (a count only)."""
    files = [p for p in paths if p.is_file()]
    return len(files), sum(sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip()) for p in files)


def summarise(name, runs, code):
    walls = [w for w, _ in runs]
    counts = [{s: r.count(s) for s in ("passed", "failed", "skipped")} for _, r in runs]
    seen: dict[str, set[str]] = defaultdict(set)
    for _, r in runs:
        for test, status in r.status.items():
            seen[test].add(status)
    flaky = sorted(t for t, s in seen.items() if {"passed", "failed"} <= s)
    always = sorted(t for t, s in seen.items() if s == {"failed"})
    files: dict[str, list[float]] = defaultdict(list)
    for _, r in runs:
        for f, c in r.files.items():
            files[f].append(c["seconds"])
    slowest = sorted(((statistics.mean(v), f) for f, v in files.items()), reverse=True)[:5]
    return {
        "name": name, "runs": len(runs), "wall_mean": statistics.mean(walls), "wall_min": min(walls), "wall_max": max(walls),
        "wall_sd": statistics.stdev(walls) if len(walls) > 1 else 0.0,
        "tests": max(sum(c.values()) for c in counts), "passed": [c["passed"] for c in counts],
        "failed": [c["failed"] for c in counts], "skipped": [c["skipped"] for c in counts],
        "flaky": flaky, "always_failed": always, "slowest": slowest, "files": code[0], "loc": code[1],
    }


def markdown(rows, workers):
    out = ["## Playwright and Selenium, compared", "",
           f"| | {' | '.join(r['name'] for r in rows)} |", f"|---|{'---|' * len(rows)}"]

    def line(label, fn):
        out.append(f"| {label} | {' | '.join(fn(r) for r in rows)} |")
    line("Runs", lambda r: str(r["runs"]))
    line(f"Wall time, mean (s), {workers} workers", lambda r: f"{r['wall_mean']:.1f}")
    line("Wall time, min-max (s)", lambda r: f"{r['wall_min']:.1f}-{r['wall_max']:.1f}")
    line("Wall time, std dev (s)", lambda r: f"{r['wall_sd']:.1f}")
    line("Tests", lambda r: str(r["tests"]))
    line("Passed per run", lambda r: ", ".join(map(str, r["passed"])))
    line("Failed per run", lambda r: ", ".join(map(str, r["failed"])))
    line("Skipped per run", lambda r: ", ".join(map(str, r["skipped"])))
    line("Flaky tests", lambda r: str(len(r["flaky"])))
    line("Failed in every run", lambda r: str(len(r["always_failed"])))
    line("Test files / non-blank lines", lambda r: f"{r['files']} / {r['loc']}")
    out += ["", "Playwright runs with `--fully-parallel` (single tests spread over the workers, as pytest-xdist "
                "does); \"per file\" is Playwright as its config stands. Wall time includes starting the browsers "
                "and, for Playwright, its own web server. Flaky: failed in some runs and passed in others."]
    for r in rows:
        out += ["", f"**{r['name']}, slowest files** (summed test time, mean per run):", ""]
        out += [f"- {f}: {secs:.1f} s" for secs, f in r["slowest"]]
        for label in ("flaky", "always_failed"):
            if r[label]:
                out += ["", f"{r['name']}, {label.replace('_', ' ')}:", ""] + [f"- {t.split(' #')[0]}" for t in r[label]]
    return "\n".join(out) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--workers", type=int, default=os.cpu_count())
    p.add_argument("--per-file", action="store_true",
                   help="also run Playwright as its config stands (a file's tests one after another)")
    p.add_argument("--only", choices=["playwright", "selenium"])
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    if not (SITE / "dist" / "index.html").is_file():
        sys.exit("site/dist holds no build: run `npm run build` in site/ first")
    playwright_code = sorted((SITE / "tests" / "ui").glob("*.ts"))
    selenium_code = sorted(p for p in HERE.glob("*.py") if p.name not in NOT_TESTS)
    suites = [("Playwright", lambda w, o: run_playwright(w, o, True), playwright_code)]
    if a.per_file:
        suites.append(("Playwright, per file", lambda w, o: run_playwright(w, o), playwright_code))
    suites.append(("Selenium", run_selenium, selenium_code))
    if a.only:
        suites = [s for s in suites if s[0].lower().startswith(a.only)]
    rows = []
    for name, runner, code in suites:
        runs = []
        for i in range(a.runs):
            with tempfile.TemporaryDirectory() as tmp:
                runs.append(runner(a.workers, Path(tmp)))
            print(f"{name} run {i + 1}/{a.runs}: {runs[-1][0]:.1f} s", file=sys.stderr, flush=True)
        rows.append(summarise(name, runs, lines_of_code(code)))
    text = markdown(rows, a.workers)
    if a.out:
        a.out.write_text(text, encoding="utf-8", newline="\n")
    report.write(text)


if __name__ == "__main__":
    main()
