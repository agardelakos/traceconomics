"""The browser tests' results as Markdown, for the run's page on GitHub ($GITHUB_STEP_SUMMARY) or the
terminal. Reads the result files the two suites write, never the tests themselves:

- Playwright's JSON report (site/test-reports/playwright.json, written by its own config);
- pytest's JUnit XML from the Selenium tests (site/selenium-report/junit.xml).

    python -I tests/selenium/report.py selenium <junit.xml>
        the Selenium section: passed, failed, skipped, time, each failure, per file
    python -I tests/selenium/report.py compare <playwright.json> <junit.xml>
        both suites from the same CI run, side by side

A missing file is reported, not skipped: a suite that never ran (an earlier step failed) is worth
seeing. Standard library only.
"""

import json
import os
import re
import sys
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Results:
    """One run of one suite."""
    status: dict[str, str] = field(default_factory=dict)          # test -> passed | failed | skipped
    errors: dict[str, str] = field(default_factory=dict)          # failed test -> first line of its error
    files: dict[str, dict[str, float]] = field(default_factory=dict)  # file -> passed, failed, skipped, seconds
    duration: float = 0.0                                          # the suite's own run time, seconds

    def count(self, kind: str) -> int:
        return sum(1 for s in self.status.values() if s == kind)


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _first_line(text) -> str:
    """An error message on one line, shortened: its lines joined, so a message whose first line is
    only a heading ("errors in the browser's console:") still says what went wrong."""
    plain = ANSI.sub("", str(text or ""))                         # no terminal colour codes
    line = " ".join(x.strip() for x in plain.splitlines() if x.strip())
    return (line[:199] + "…" if len(line) > 200 else line).replace("|", "\\|")


def _tally(r: Results, file: str, status: str, seconds: float):
    f = r.files.setdefault(file, {"passed": 0, "failed": 0, "skipped": 0, "seconds": 0.0})
    f[status] += 1
    f["seconds"] += seconds


def playwright(path: Path) -> Results | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    r = Results(duration=(data.get("stats", {}).get("duration") or 0) / 1000)

    def walk(suite, file=None, titles=()):
        file = suite.get("file") or file
        titles = (*titles, suite["title"]) if suite.get("title") and suite.get("title") != file else titles
        for spec in suite.get("specs", []):
            for n, test in enumerate(spec.get("tests", [])):
                # Titles can repeat (in other describe blocks, or as repeated specs): the key keeps them apart.
                name = " › ".join([file, *titles, spec["title"]])
                key = f"{name} [{test.get('projectName', '')}] #{spec.get('id', '')}{n}"
                runs = test.get("results", [])
                kind = test.get("status") or (runs[-1]["status"] if runs else "skipped")
                status = {"expected": "passed", "passed": "passed", "skipped": "skipped"}.get(kind, "failed")
                r.status[key] = status
                if status == "failed":
                    r.errors[name] = _first_line(next((x["error"].get("message") for x in runs if x.get("error")), ""))
                _tally(r, file, status, sum(x.get("duration", 0) for x in runs) / 1000)
        for child in suite.get("suites", []):
            walk(child, file, titles)
    for suite in data.get("suites", []):
        walk(suite)
    for e in data.get("errors", []):
        r.errors["(outside the tests)"] = _first_line(e.get("message"))
    return r


def selenium(path: Path) -> Results | None:
    if not path.is_file():
        return None
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    r = Results(duration=sum(float(s.get("time", 0)) for s in suites))
    for case in root.iter("testcase"):
        file = case.get("classname", "").split(".")[-1] + ".py"
        name = f"{file} › {case.get('name')}"
        bad = next((c for c in case if c.tag in ("failure", "error")), None)
        status = "failed" if bad is not None else "skipped" if case.find("skipped") is not None else "passed"
        r.status[name] = status
        if bad is not None:
            prefix = "error in setup or teardown: " if bad.tag == "error" else ""
            r.errors[name] = prefix + _first_line(bad.get("message") or bad.text)
        _tally(r, file, status, float(case.get("time", 0)))
    return r


def _bold(n: int) -> str:
    return f"**{n}**" if n else "0"


def selenium_section(r: Results | None) -> str:
    lines = ["## Browser tests (Selenium)", ""]
    if r is None:
        return "\n".join(lines + ["No results: it didn't run (an earlier step failed).", ""])
    lines += ["| Passed | Failed | Skipped | Time |", "|---:|---:|---:|---:|",
              f"| {r.count('passed')} | {_bold(r.count('failed'))} | {r.count('skipped')} | {r.duration:.0f} s |"]
    if r.count("skipped"):
        lines += ["", "Skipped: the tests of the host's own headers, which need a server that applies them (`--base-url`)."]
    lines += ["", "<details><summary>By test file</summary>", "", "| File | Passed | Failed | Skipped | Summed test time |",
              "|---|---:|---:|---:|---:|"]
    lines += [f"| {f} | {c['passed']} | {_bold(c['failed'])} | {c['skipped']} | {c['seconds']:.1f} s |" for f, c in sorted(r.files.items())]
    lines += ["", "</details>"]
    if r.errors:
        lines += ["", "### Failures", ""] + [f"- {name}: {error}" for name, error in r.errors.items()]
    lines += ["", "Every test with its time, and for a failure its screenshot, page and console, is attached to this run as "
              "`selenium-report` (kept 7 days)."]
    return "\n".join(lines) + "\n"


def compare_section(pw: Results | None, se: Results | None) -> str:
    lines = ["## Playwright and Selenium, this run", ""]
    if pw is None or se is None:
        missing = " and ".join(n for n, r in (("Playwright", pw), ("Selenium", se)) if r is None)
        return "\n".join(lines + [f"No comparison: no results from {missing}.", ""])
    rows = [
        ("Passed", lambda r: str(r.count("passed"))),
        ("Failed", lambda r: _bold(r.count("failed"))),
        ("Skipped", lambda r: str(r.count("skipped"))),
        ("Suite time", lambda r: f"{r.duration:.0f} s"),
        ("Summed test time", lambda r: f"{sum(c['seconds'] for c in r.files.values()):.0f} s"),
        ("Test files", lambda r: str(len(r.files))),
    ]
    lines += ["| | Playwright | Selenium |", "|---|---:|---:|"]
    lines += [f"| {label} | {fn(pw)} | {fn(se)} |" for label, fn in rows]
    for name, r in (("Playwright", pw), ("Selenium", se)):
        slow = sorted(r.files.items(), key=lambda kv: -kv[1]["seconds"])[:3]
        lines += ["", f"{name}, slowest files: " + ", ".join(f"{f} ({c['seconds']:.0f} s)" for f, c in slow)]
    lines += ["", "Not like for like: each suite ran in its own job on its own runner. Playwright ran the coverage "
              "build and runs a file's tests one after another; Selenium spreads single tests over the workers. "
              "For a fair comparison (several runs, the same machine and workers, Playwright with `--fully-parallel`), "
              "run the `compare` workflow."]
    return "\n".join(lines) + "\n"


def write(text: str):
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8", newline="\n") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


def main(argv: list[str]):
    if argv[:1] == ["selenium"] and len(argv) == 2:
        write(selenium_section(selenium(Path(argv[1]))))
    elif argv[:1] == ["compare"] and len(argv) == 3:
        write(compare_section(playwright(Path(argv[1])), selenium(Path(argv[2]))))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
