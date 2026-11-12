"""Run history: each suite run as one record, kept per trigger, with the catalog it ran against.

    python -I tests/catalog/history.py record --catalog catalog.json --out record.json
        --trigger push --commit SHA [--build ID] [--run-id N] [--run-url URL]
        [--env platform=… --env browser=… --env data=made-up]
        [--junit pytest=tests.xml] [--junit pytest-local=local.xml] [--junit selenium=junit.xml]
        [--playwright playwright.json] [--vitest vitest.json]

    python -I tests/catalog/history.py append --store DIR record.json [--catalog catalog.json] [--keep 200]

`record` reads the result files the suites already write (JUnit XML from pytest, Playwright's
JSON report, Vitest's JSON report) and gives each result to its case: through the catalog for
pytest and Selenium, through the test's own annotations or `meta` for Playwright and Vitest. A
test without a case is counted per suite, so the record shows how far the backfill has come.

`append` adds a record to the store (the branch `test-history`, checked out at DIR):

    runs/<trigger>/<started>_<run id>.json   one file per run; the oldest beyond --keep removed
    catalog.json                             the catalog of the newest push to main
    obsolete.json                            every ID whose test was removed, with the last commit
                                             that had it; never shrinks, so an ID is never reused

A case's result in a run: failed if any example failed; flaky if one passed only on a retry;
skipped if every example was skipped; otherwise passed.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ElementTree
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cases import from_annotations, from_meta  # noqa: E402

TRIGGERS = ("push", "ui-test", "smoke", "promote")
SAFE = re.compile(r"[^A-Za-z0-9._-]")
RANK = {"failed": 3, "flaky": 2, "passed": 1, "skipped": 0}


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Run:
    """Results being gathered into one record."""

    def __init__(self):
        self.cases: dict[str, dict] = {}
        self.suites: dict[str, dict] = {}
        self.no_case: dict[str, int] = {}

    def add(self, suite: str, case_id: str | None, example: str, result: str, seconds: float, retries: int = 0):
        s = self.suites.setdefault(suite, {"passed": 0, "failed": 0, "flaky": 0, "skipped": 0, "duration": 0.0})
        s[result] += 1
        s["duration"] = round(s["duration"] + seconds, 3)
        if not case_id:
            self.no_case[suite] = self.no_case.get(suite, 0) + 1
            return
        c = self.cases.setdefault(
            case_id, {"suite": suite, "result": "skipped", "duration": 0.0, "retries": 0, "examples": {}}
        )
        # The same example twice (a file run by both pytest jobs, a repeated title): the worse result
        # stands, so a failure is never hidden by a later pass.
        before = c["examples"].get(example)
        c["examples"][example] = result if before is None else max(before, result, key=RANK.get)
        c["duration"] = round(c["duration"] + seconds, 3)
        c["retries"] += retries

    def finish(self):
        for c in self.cases.values():
            results = set(c["examples"].values())
            c["result"] = max(results - {"skipped"} or {"skipped"}, key=RANK.get)
            if len(c["examples"]) == 1:
                c.pop("examples")  # not an outline: the result says it all


def junit_index(catalog: dict, suite: str) -> dict[tuple[str, str], str]:
    """(JUnit classname, test name without parameters) → case ID, from the catalog's node IDs."""
    out = {}
    for c in catalog["cases"]:
        if c["suite"] != suite or not c["id"]:
            continue
        path, *rest = c["node"].split("::")
        classname = path.removesuffix(".py").replace("/", ".") + "".join("." + r for r in rest[:-1])
        out[(classname, rest[-1] if rest else "")] = c["id"]
    return out


def read_junit(run: Run, path: Path, suite: str, catalog: dict):
    # `pytest-local` (the microdata tests, run in their own job) are pytest cases in the catalog.
    index = junit_index(catalog, suite.split("-", 1)[0])
    for tc in ElementTree.parse(path).getroot().iter("testcase"):
        name = tc.get("name", "")
        if not name:
            # A module that skipped itself whole (`pytest.importorskip` at its top) appears as one
            # nameless entry: not a test. Its tests run, and are recorded, where the skip doesn't apply.
            continue
        base, _, param = name.partition("[")
        param = param.removesuffix("]")
        if tc.find("failure") is not None or tc.find("error") is not None:
            result = "failed"
        elif tc.find("skipped") is not None:
            result = "skipped"
        else:
            result = "passed"
        case_id = index.get((tc.get("classname", ""), base))
        run.add(suite, case_id, param or base, result, float(tc.get("time") or 0))


def read_playwright(run: Run, data: dict):
    def walk(suite, titles=()):
        if suite.get("title") and suite["title"] != suite.get("file"):  # a describe block, not the file
            titles = (*titles, suite["title"])
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                d = from_annotations(test.get("annotations", []))
                results = test.get("results", [])
                status = test.get("status")
                result = {"expected": "passed", "skipped": "skipped", "flaky": "flaky"}.get(status, "failed")
                # The describe titles too: the same test title can sit in two describe blocks.
                example = " › ".join([*titles, spec["title"]]) + (
                    f" [{test['projectName']}]" if test.get("projectName") not in (None, "", "chromium") else ""
                )
                run.add(
                    "playwright",
                    d["id"],
                    example,
                    result,
                    sum(r.get("duration", 0) for r in results) / 1000,
                    max(len(results) - 1, 0),
                )
        for child in suite.get("suites", []):
            walk(child, titles)

    for s in data.get("suites", []):
        walk(s)


def read_vitest(run: Run, data: dict):
    for f in data.get("testResults", []):
        for a in f.get("assertionResults", []):
            status = a.get("status")
            result = "passed" if status == "passed" else "failed" if status == "failed" else "skipped"
            example = " › ".join([*a.get("ancestorTitles", []), a.get("title", "")])
            run.add("vitest", from_meta(a.get("meta"))["id"], example, result, (a.get("duration") or 0) / 1000)


def record(a) -> dict:
    catalog = json.loads(a.catalog.read_text(encoding="utf-8"))
    run = Run()
    for spec in a.junit or []:
        suite, _, path = spec.partition("=")
        read_junit(run, Path(path), suite, catalog)
    if a.playwright:
        read_playwright(run, json.loads(a.playwright.read_text(encoding="utf-8")))
    if a.vitest:
        read_vitest(run, json.loads(a.vitest.read_text(encoding="utf-8")))
    run.finish()
    env = dict(e.split("=", 1) for e in a.env or [])
    return {
        "schema": 1,
        "run_id": a.run_id,
        "trigger": a.trigger,
        "commit": a.commit,
        "build": a.build,
        "started": a.started or now(),
        "environment": env,
        "suites": run.suites,
        "no_case": run.no_case,
        "cases": dict(sorted(run.cases.items())),
        "report": a.run_url,
    }


def check_record(r: dict) -> list[str]:
    """What makes a record unusable. Records from outside CI (the release builds) are checked
    before they are stored: a bad one is reported and left out, never half-stored."""
    problems = []
    if r.get("schema") != 1:
        problems.append("unknown schema")
    if r.get("trigger") not in TRIGGERS:
        problems.append(f"unknown trigger {r.get('trigger')!r}")
    if not re.fullmatch(r"[0-9a-f]{7,40}", str(r.get("commit") or "")):
        problems.append("no commit")
    try:
        datetime.strptime(r.get("started") or "", "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        problems.append("no start time")
    if not isinstance(r.get("cases"), dict) or not isinstance(r.get("suites"), dict):
        problems.append("no results")
    else:
        for cid, c in r["cases"].items():
            if not isinstance(c, dict) or c.get("result") not in RANK:
                problems.append(f"{cid}: not a case result")
                break
            if c.get("result") not in RANK:
                problems.append(f"{cid}: unknown result {c.get('result')!r}")
                break
    return problems


def append(store: Path, rec: dict, catalog: dict | None, keep: int) -> Path:
    problems = check_record(rec)
    if problems:
        raise ValueError("; ".join(problems))
    folder = store / "runs" / rec["trigger"]
    folder.mkdir(parents=True, exist_ok=True)
    name = rec["started"].replace(":", "-") + "_" + SAFE.sub("-", str(rec.get("run_id") or rec.get("build") or "run"))
    path = folder / f"{name}.json"
    write(path, rec)
    for old in sorted(folder.glob("*.json"))[:-keep] if keep > 0 else []:
        old.unlink()
    if catalog is not None:
        update_catalog(store, catalog)
    return path


def update_catalog(store: Path, new: dict):
    """The newer catalog replaces the stored one; IDs that disappeared become obsolete.

    The caller passes a catalog only from a run whose catalog check passed, and only when its commit
    descends from the stored one (test_history_push.sh): an old run re-run never rolls the catalog
    back. A suite the new catalog says it couldn't collect (`missing`) keeps its stored cases, so
    its IDs are not taken for removed. A case that comes back in the same suite, file and title (a
    revert) is taken off the obsolete list; anything else under an old ID is a reuse, which the
    validator refuses."""
    old_path, obs_path = store / "catalog.json", store / "obsolete.json"
    obsolete = json.loads(obs_path.read_text(encoding="utf-8")) if obs_path.is_file() else {}
    missing = set(new.get("missing", []))
    if old_path.is_file():
        old = json.loads(old_path.read_text(encoding="utf-8"))
        kept = [c for c in old["cases"] if c["suite"] in missing]
        new = {**new, "cases": new["cases"] + kept}
        now_ids = {c["id"] for c in new["cases"] if c["id"]}
        for c in old["cases"]:
            if c["id"] and c["id"] not in now_ids and c["id"] not in obsolete:
                obsolete[c["id"]] = {
                    "suite": c["suite"],
                    "title": c["title"],
                    "file": c["file"],
                    "last_commit": old.get("commit"),
                    "removed_in": new.get("commit"),
                }
    for c in new["cases"]:
        o = obsolete.get(c["id"])
        if o and (o["suite"], o["file"], o["title"]) == (c["suite"], c["file"], c["title"]):
            del obsolete[c["id"]]
    write(old_path, new)
    write(obs_path, dict(sorted(obsolete.items())))


def write(path: Path, data):
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--catalog", required=True, type=Path)
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--trigger", required=True, choices=TRIGGERS)
    r.add_argument("--commit", required=True)
    r.add_argument("--build")
    r.add_argument("--run-id")
    r.add_argument("--run-url")
    r.add_argument("--started")
    r.add_argument("--env", action="append", help="key=value, e.g. platform=linux-x86_64")
    r.add_argument("--junit", action="append", help="suite=path to a JUnit XML file")
    r.add_argument("--playwright", type=Path)
    r.add_argument("--vitest", type=Path)
    p = sub.add_parser("append")
    p.add_argument("--store", required=True, type=Path)
    p.add_argument("record", type=Path)
    p.add_argument("--catalog", type=Path, help="the catalog of this run (pushes to main only)")
    p.add_argument("--keep", type=int, default=200)
    a = ap.parse_args(argv)
    if a.cmd == "record":
        rec = record(a)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        write(a.out, rec)
        n = sum(s["passed"] + s["failed"] + s["flaky"] + s["skipped"] for s in rec["suites"].values())
        print(f"{n} results, {len(rec['cases'])} cases, without a case: {sum(rec['no_case'].values())}")
    else:
        rec = json.loads(a.record.read_text(encoding="utf-8"))
        catalog = json.loads(a.catalog.read_text(encoding="utf-8")) if a.catalog else None
        try:
            print(append(a.store, rec, catalog, a.keep))
        except ValueError as e:
            sys.exit(f"record refused: {e}")


if __name__ == "__main__":
    main()
