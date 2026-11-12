"""Runs the site's two browser suites, Playwright (site/tests/ui) and Selenium (tests/selenium), several
times each on the same build and the same number of workers, and writes a Markdown comparison:
wall time, tests run, failures, flaky tests (failed in some runs, passed in others), the slowest
files, and lines of test code.

The Playwright suite is run as a black box through its own npm script and JSON reporter. Its config
spreads single tests over the workers (`fullyParallel`), as pytest-xdist does, so the times compare
like for like; the `--fully-parallel` flag is passed as well, to say so. `--per-file` adds the other
mode for both tools: Playwright with `UI_PER_FILE=on`, which runs the tests of one file one after
another in one worker, and Selenium with pytest-xdist's `--dist loadfile`, which sends all the tests
of one file to the same worker.
`--sequential` adds both suites run one test at a time (Playwright `--workers=1`, pytest `-n 0`).

    python -I tests/compare/compare.py --runs 5 [--workers 8] [--per-file] [--sequential] [--out comparison.md]

Both suites run on the made-up data (`tests/sitedata.py`), so every comparison, here or in CI, tests
the same pages with the same numbers. Before the runs, the script writes that data afresh into a
temporary folder and refuses to go on unless the build's data match it (`--any-data` skips the check,
for a look at other data; the report then says so). To build on it:

    python tests/sitedata.py site/public/data    (this replaces the data in site/public/data)
    npm run build                                 (in site/)

On GitHub its output also goes on the run's page. Standard library only.

It lives apart from both suites (tests/selenium, site/tests/ui), as the one place that knows both.
"""

import argparse
import hashlib
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
SELENIUM = ROOT / "tests" / "selenium"
# The made-up data are the same on every run except the generation time in metadata.json and the
# checksum file that covers it; the fingerprint leaves both out.
NOT_FINGERPRINTED = {"metadata.json", "SHA256SUMS"}

# Where each scheduling mode is documented (checked 2026-11-04).
DOCS = {
    "playwright": "https://playwright.dev/docs/test-parallel#parallelize-tests-in-a-single-file",
    "playwright_cli": "https://playwright.dev/docs/test-cli",
    "playwright_by_file": "https://playwright.dev/docs/test-parallel#introduction",
    "playwright_workers": "https://playwright.dev/docs/test-parallel#worker-processes",
    "xdist": "https://pytest-xdist.readthedocs.io/en/stable/distribution.html#distribution-modes",
    "xdist_workers": "https://pytest-xdist.readthedocs.io/en/stable/distribution.html",
    "playwright_sequential": "https://playwright.dev/docs/test-parallel#disable-parallelism",
    "xdist_sequential": "https://pytest-xdist.readthedocs.io/en/stable/distribution.html#running-tests-across-multiple-cpus",
}


def run_playwright(workers: int, out: Path, fully_parallel: bool = False) -> tuple[float, report.Results]:
    path = out / "playwright.json"
    env = {**os.environ, "PLAYWRIGHT_JSON_OUTPUT_FILE": str(path)}
    env.pop("TRACECONOMICS_COVERAGE", None)  # a plain build, as the Selenium suite gets
    if not fully_parallel:
        env["UI_PER_FILE"] = "on"  # the config spreads single tests unless told otherwise
    npm = shutil.which("npm") or "npm"
    args = [npm, "run", "test:ui", "--", "--reporter=json", f"--workers={workers}"] + (
        ["--fully-parallel"] if fully_parallel else []
    )
    start = time.monotonic()
    subprocess.run(args, cwd=SITE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return time.monotonic() - start, report.playwright(path) or report.Results()


def run_selenium(workers: int, out: Path, by_file: bool = False) -> tuple[float, report.Results]:
    path = out / "junit.xml"
    # "load" hands out single tests (xdist's default); "loadfile" keeps each file on one worker.
    # 0 workers: xdist off, every test in the main process, one after another.
    spread = ["-n", "0"] if workers == 0 else ["-n", str(workers), "--dist", "loadfile" if by_file else "load"]
    start = time.monotonic()
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            "tests/selenium",
            "--selenium",
            *spread,
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={path}",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return time.monotonic() - start, report.selenium(path) or report.Results()


def fingerprint(folder: Path) -> str:
    """SHA-256 over every data file's path and bytes, in a fixed order (see NOT_FINGERPRINTED)."""
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and p.name not in NOT_FINGERPRINTED):
        digest.update(path.relative_to(folder).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def made_up_fingerprint() -> str:
    """The fingerprint of the made-up data, written afresh by tests/sitedata.py."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [sys.executable, str(ROOT / "tests" / "sitedata.py"), tmp], cwd=ROOT, stdout=subprocess.DEVNULL, check=True
        )
        return fingerprint(Path(tmp))


def lines_of_code(paths: list[Path]) -> tuple[int, int]:
    """Files and non-blank lines (a count only)."""
    files = [p for p in paths if p.is_file()]
    return len(files), sum(sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip()) for p in files)


def summarise(name, url, runs, code):
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
        "name": name,
        "url": url,
        "runs": len(runs),
        "wall_mean": statistics.mean(walls),
        "wall_min": min(walls),
        "wall_max": max(walls),
        "wall_sd": statistics.stdev(walls) if len(walls) > 1 else 0.0,
        "tests": max(sum(c.values()) for c in counts),
        "passed": [c["passed"] for c in counts],
        "failed": [c["failed"] for c in counts],
        "skipped": [c["skipped"] for c in counts],
        "flaky": flaky,
        "always_failed": always,
        "slowest": slowest,
        "files": code[0],
        "loc": code[1],
    }


def _header(row) -> str:
    """A column's name, linked to the documentation of how that suite was scheduled."""
    return f"[{row['name']}]({row['url']})" if row.get("url") else row["name"]


def markdown(rows, workers, data: str):
    out = [
        "## Playwright and Selenium, compared",
        "",
        data,
        "",
        f"| | {' | '.join(map(_header, rows))} |",
        f"|---|{'---|' * len(rows)}",
    ]

    def line(label, fn):
        out.append(f"| {label} | {' | '.join(fn(r) for r in rows)} |")

    line("Runs", lambda r: str(r["runs"]))
    line("Wall time, mean (s)", lambda r: f"{r['wall_mean']:.1f}")
    line("Wall time, min-max (s)", lambda r: f"{r['wall_min']:.1f}-{r['wall_max']:.1f}")
    line("Wall time, std dev (s)", lambda r: f"{r['wall_sd']:.1f}")
    line("Tests", lambda r: str(r["tests"]))
    line("Passed per run", lambda r: ", ".join(map(str, r["passed"])))
    line("Failed per run", lambda r: ", ".join(map(str, r["failed"])))
    line("Skipped per run", lambda r: ", ".join(map(str, r["skipped"])))
    line("Flaky tests", lambda r: str(len(r["flaky"])))
    line("Failed in every run", lambda r: str(len(r["always_failed"])))
    line("Test files / non-blank lines", lambda r: f"{r['files']} / {r['loc']}")
    for r in rows:
        out += ["", f"**{r['name']}, slowest files** (summed test time, mean per run):", ""]
        out += [f"- {f}: {secs:.1f} s" for secs, f in r["slowest"]]
        for label in ("flaky", "always_failed"):
            if r[label]:
                out += ["", f"{r['name']}, {label.replace('_', ' ')}:", ""] + [
                    f"- {t.split(' #')[0]}" for t in r[label]
                ]
    out += ["", *explanations(workers)]
    return "\n".join(out) + "\n"


def explanations(workers: int) -> list[str]:
    """What each column and row means, folded under the table (GitHub shows <details> as a fold)."""
    return [
        "<details><summary>What the columns and rows mean</summary>",
        "",
        "**Columns**",
        "",
        f"- **Playwright parallel ({workers} workers)**: the Playwright suite with its `--fully-parallel` flag, so "
        "single tests are spread over the workers, as pytest-xdist does for Selenium. This and Selenium are the "
        f"like-for-like pair. Docs: [fullyParallel]({DOCS['playwright']}), [the --fully-parallel flag]({DOCS['playwright_cli']}).",
        f"- **Playwright parallel by file ({workers} workers)** (only with `--per-file`): Playwright with "
        f"`UI_PER_FILE=on`, Playwright's own default. Up to {workers} files run at once, but the tests of one file run one after another in a single "
        f"worker, so the longest file sets the time. Docs: [Playwright's default]({DOCS['playwright_by_file']}).",
        f"- **Selenium parallel ({workers} workers)**: the Python suite (tests/selenium), single tests spread over "
        f"the workers by pytest-xdist (`--dist load`, its default). Docs: [distribution modes]({DOCS['xdist']}).",
        f"- **Selenium parallel by file ({workers} workers)** (only with `--per-file`): the same suite with "
        "pytest-xdist's `--dist loadfile`: all the tests of one file go to the same worker, as in Playwright's "
        'default. The two "by file" columns are the other like-for-like pair. '
        f"Docs: [distribution modes]({DOCS['xdist']}).",
        "- **Playwright sequential (1 worker)** (only with `--sequential`): one test at a time, with "
        f"`--workers=1`. Docs: [disable parallelism]({DOCS['playwright_sequential']}).",
        "- **Selenium sequential (1 worker)** (only with `--sequential`): one test at a time, with `-n 0`: "
        "pytest-xdist off, every test in the main process. "
        f"Docs: [-n 0]({DOCS['xdist_sequential']}). The two sequential columns show each suite's total work "
        "without any parallelism: the time a single machine thread needs for it.",
        f"- **{workers} workers**: each parallel column ran up to {workers} tests at once, each worker with its own browser "
        f"(the default is one per CPU). Docs: [Playwright workers]({DOCS['playwright_workers']}), "
        f"[pytest-xdist -n]({DOCS['xdist_workers']}).",
        "",
        "**Rows**",
        "",
        "- **Runs**: how many times each suite ran, on the same build and data. Repeats show how steady the "
        "times are and catch flaky tests.",
        "- **Wall time, mean (s)**: the real time from starting a suite until it finished, as a clock on the "
        "wall shows it (not the sum of every test's own time), averaged over the runs. It includes starting the "
        "browsers and, for Playwright, its own web server.",
        "- **Wall time, min-max (s)**: the fastest and the slowest run. A narrow range means a steady suite.",
        "- **Wall time, std dev (s)**: the standard deviation, roughly how far a typical run lands from the mean. "
        "Close to 0 means nearly every run took the same time.",
        "- **Tests**: the tests in each suite, skipped ones included. The suites were written independently, so "
        "this is not a like-for-like count, and the time per test is not strictly comparable either.",
        "- **Passed per run**: the tests that passed, one number per run, in order.",
        "- **Failed per run**: the tests that failed or errored, one number per run. All zeros: every run was clean.",
        "- **Skipped per run**: tests left out on purpose. Selenium's are the host tests (security headers, CORS, "
        "the content security policy on every page): they need a server that sends the site's headers "
        "(`--base-url`), which the test process's own small server doesn't.",
        "- **Flaky tests**: tests that failed in some runs and passed in others, so their failures can't be "
        "trusted. They are listed by name below the table.",
        "- **Failed in every run**: tests that failed every time: a real fault in the site or in the test, not "
        "flakiness. Also listed by name.",
        "- **Test files / non-blank lines**: how much test code each suite takes, counting lines that aren't "
        "empty. Selenium's include its helpers, which do by hand what Playwright does for you (waiting, failure "
        "messages, a static server). The tools (compare.py, report.py) are not counted.",
        "- **Slowest files (summed test time, mean per run)**: each file's tests' own durations added up, "
        "averaged over the runs. This is total work, not elapsed time: a file can sum to more than the whole "
        "suite's wall time when its tests ran in parallel. In \"by file\" mode the slowest file's sum is close "
        "to the wall time, because that file ran in one worker, and that is why the mode is slow.",
        "",
        "</details>",
    ]


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--workers", type=int, default=os.cpu_count())
    p.add_argument(
        "--per-file",
        action="store_true",
        help="also run both suites by file (a file's tests one after another in one worker)",
    )
    p.add_argument("--sequential", action="store_true", help="also run both suites one test at a time (1 worker)")
    p.add_argument("--only", choices=["playwright", "selenium"])
    p.add_argument(
        "--any-data", action="store_true", help="run on whatever data the build holds, not only the made-up data"
    )
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    if not (SITE / "dist" / "index.html").is_file():
        sys.exit("site/dist holds no build: run `npm run build` in site/ first")
    built = fingerprint(SITE / "dist" / "data")
    if a.any_data:
        data = f"Data: as built, not checked against the made-up data (`--any-data`); fingerprint `{built[:16]}`."
    else:
        print("checking the build's data against the made-up data...", file=sys.stderr, flush=True)
        if built != made_up_fingerprint():
            sys.exit(
                "site/dist/data are not the made-up data. Run `python tests/sitedata.py site/public/data` "
                "(it replaces that folder's data), then `npm run build` in site/; or pass --any-data"
            )
        data = f"Data: the made-up data (`tests/sitedata.py`); fingerprint `{built[:16]}`."
    playwright_code = sorted((SITE / "tests" / "ui").glob("*.ts"))
    selenium_code = sorted(SELENIUM.glob("*.py"))
    # The worker count goes into each column's name, so a saved report says how it was run.
    n = a.workers
    # The like-for-like pairs side by side: single tests spread over the workers, then by file.
    suites = [
        (
            f"Playwright parallel ({n} workers)",
            DOCS["playwright"],
            lambda w, o: run_playwright(w, o, True),
            playwright_code,
        ),
        (f"Selenium parallel ({n} workers)", DOCS["xdist"], lambda w, o: run_selenium(w, o), selenium_code),
    ]
    if a.per_file:
        suites += [
            (
                f"Playwright parallel by file ({n} workers)",
                DOCS["playwright_by_file"],
                lambda w, o: run_playwright(w, o),
                playwright_code,
            ),
            (
                f"Selenium parallel by file ({n} workers)",
                DOCS["xdist"],
                lambda w, o: run_selenium(w, o, True),
                selenium_code,
            ),
        ]
    if a.sequential:
        # One test at a time: Playwright with a single worker, Selenium with xdist off.
        suites += [
            (
                "Playwright sequential (1 worker)",
                DOCS["playwright_sequential"],
                lambda w, o: run_playwright(1, o),
                playwright_code,
            ),
            (
                "Selenium sequential (1 worker)",
                DOCS["xdist_sequential"],
                lambda w, o: run_selenium(0, o),
                selenium_code,
            ),
        ]
    if a.only:
        suites = [s for s in suites if s[0].lower().startswith(a.only)]
    rows = []
    for name, url, runner, code in suites:
        runs = []
        for i in range(a.runs):
            with tempfile.TemporaryDirectory() as tmp:
                runs.append(runner(a.workers, Path(tmp)))
            print(f"{name} run {i + 1}/{a.runs}: {runs[-1][0]:.1f} s", file=sys.stderr, flush=True)
        rows.append(summarise(name, url, runs, lines_of_code(code)))
    text = markdown(rows, a.workers, data)
    if a.out:
        a.out.write_text(text, encoding="utf-8", newline="\n")
    report.write(text)


if __name__ == "__main__":
    main()
