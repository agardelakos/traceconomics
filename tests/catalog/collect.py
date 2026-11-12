"""The test catalog: every case of the four suites, read from the tests, as one JSON file.

    python -I tests/catalog/collect.py --out catalog.json [--no-selenium]
        [--playwright list.json] [--vitest vitest.json] [--commit SHA]

- pytest and Selenium are collected here (`pytest --collect-only` with the `pytest_catalog`
  plugin; nothing runs). Selenium needs the `selenium` extra; `--no-selenium` leaves it out.
- Playwright: the output of `npx playwright test --list --reporter=json` (in `site/`, with data
  files present: the specs read them while they are collected).
- Vitest: a run's JSON report (`npx vitest run --reporter=json --outputFile=…`). Vitest's own
  list leaves out the `meta` that holds the case, so the catalog reads a run.

A suite whose input isn't given is left out and named in the file's `missing` list, so the
validator can say the catalog is incomplete instead of passing it.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cases import Case, from_annotations, from_docstring, from_meta, issues  # noqa: E402

ROOT = HERE.parent.parent
# Marks that aren't tags: pytest's own, and the ones that carry defect links.
PYTEST_MARKS = {"parametrize", "usefixtures", "filterwarnings", "skip", "skipif", "xfail"}


def _rel(path: str | Path, base: Path = ROOT) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = base / p
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def pytest_items(args: list[str]) -> list[dict]:
    """Run pytest's collection with the plugin and return what it wrote."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "items.json"
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [str(HERE), os.environ.get("PYTHONPATH")])))
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "pytest_catalog",
            "--catalog-out",
            str(out),
            "-p",
            "no:cacheprovider",
            *args,
        ]
        done = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
        if done.returncode not in (0, 5) or not out.is_file():  # 5: nothing collected
            sys.exit(f"pytest collection failed ({' '.join(args)}):\n{done.stdout[-3000:]}\n{done.stderr[-3000:]}")
        return json.loads(out.read_text(encoding="utf-8"))["items"]


def from_pytest(items: list[dict], suite: str) -> list[Case]:
    """One Case per test function; a parametrized one is an outline, its parameter IDs the examples."""
    by_node: dict[str, Case] = {}
    for it in items:
        c = by_node.get(it["base"])
        if c is None:
            d = from_docstring(it["doc"])
            reasons = " ".join(it["reasons"])
            c = by_node[it["base"]] = Case(
                id=d["id"],
                suite=suite,
                title=d["title"],
                file=_rel(it["file"]),
                line=it["line"],
                node=it["base"],
                given=d["given"],
                when=d["when"],
                then=d["then"],
                notes=d["notes"],
                defects=issues(reasons),
                tags=[m for m in it["markers"] if m not in PYTEST_MARKS],
                problems=d["problems"],
            )
        if it["param"] is not None:
            c.examples.append(it["param"])
    return list(by_node.values())


def from_playwright(listing: dict) -> list[Case]:
    root = Path(listing.get("config", {}).get("rootDir") or ROOT / "site/tests/ui")
    out: list[Case] = []

    def walk(suite, file=None, titles=()):
        file = suite.get("file") or file
        title = suite.get("title")
        if title and title != file and not suite.get("file"):
            titles = (*titles, title)
        for spec in suite.get("specs", []):
            for test in spec.get("tests", [])[:1]:  # one entry per project; the case is the same
                d = from_annotations(test.get("annotations", []))
                path = _rel(root / (spec.get("file") or file))
                out.append(
                    Case(
                        id=d["id"],
                        suite="playwright",
                        title=d["title"] or spec["title"],
                        named=bool(d["title"]),
                        file=path,
                        line=spec.get("line", 0),
                        node=" › ".join([path, *titles, spec["title"]]),
                        given=d["given"],
                        when=d["when"],
                        then=d["then"],
                        defects=d["defects"],
                        tags=sorted(t.lstrip("@") for t in spec.get("tags", [])),
                        problems=d["problems"],
                    )
                )
        for child in suite.get("suites", []):
            walk(child, file, titles)

    for s in listing.get("suites", []):
        walk(s)
    return out


def from_vitest(report: dict) -> list[Case]:
    out: list[Case] = []
    for f in report.get("testResults", []):
        path = _rel(f["name"])
        for a in f.get("assertionResults", []):
            d = from_meta(a.get("meta"))
            loc = a.get("location") or {}
            out.append(
                Case(
                    id=d["id"],
                    suite="vitest",
                    title=d["title"] or a.get("title", ""),
                    named=bool(d["title"]),
                    file=path,
                    line=loc.get("line", 0),
                    node=" › ".join([path, *a.get("ancestorTitles", []), a.get("title", "")]),
                    given=d["given"],
                    when=d["when"],
                    then=d["then"],
                    tags=list(a.get("tags") or []),
                    problems=d["problems"],
                )
            )
    return out


def merge_outlines(cases: list[Case]) -> list[Case]:
    """Playwright and Vitest tests in one file that share an ID and its steps are one outline (a
    loop over languages, `test.each`): their titles become its examples. Anything else under one ID
    stays apart, so the validator reports it as a duplicate: two pytest or Selenium functions (a
    parametrize is already one outline there), or examples whose steps differ (a copied test whose
    ID was left as it was)."""
    merged: dict[tuple, Case] = {}
    out: list[Case] = []
    for c in cases:
        if c.id is None:
            out.append(c)
            continue
        key = (c.suite, c.id, c.file)
        first = merged.get(key)
        if (
            first is None
            or c.suite in ("pytest", "selenium")
            or (c.given, c.when, c.then) != (first.given, first.when, first.then)
        ):
            merged.setdefault(key, c)
            out.append(c)
            continue
        if not first.examples:
            first.examples.append(first.node.rsplit(" › ", 1)[-1])
        first.examples += c.examples or [c.node.rsplit(" › ", 1)[-1]]
        first.defects = sorted(set(first.defects) | set(c.defects))
        first.tags = sorted(set(first.tags) | set(c.tags))
    for c in out:
        if c.id and len(c.examples) > 1 and c.suite in ("playwright", "vitest") and not c.named:
            c.title = shared_title(c.examples) or c.title
    return out


def shared_title(titles: list[str]) -> str:
    """What an outline's example titles have in common: `en: untouched, …` and `el: untouched, …`
    give `untouched, …`. Empty when they share too little to name the case."""

    def common(a: str, b: str) -> str:
        n = 0
        while n < min(len(a), len(b)) and a[n] == b[n]:
            n += 1
        return a[:n]

    suffix = titles[0][::-1]
    prefix = titles[0]
    for x in titles[1:]:
        suffix = common(suffix, x[::-1])
        prefix = common(prefix, x)
    best = max(suffix[::-1], prefix, key=len).strip(" :,;-–›")
    return best if len(best) >= 12 else ""


def catalog(cases: list[Case], missing: list[str], commit: str | None) -> dict:
    cases = merge_outlines(cases)
    cases.sort(key=lambda c: (c.suite, c.file, c.line, c.node))
    return {
        "schema": 1,
        "commit": commit,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "missing": missing,
        "cases": [c.to_json() for c in cases],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--playwright", type=Path, help="playwright --list --reporter=json output")
    ap.add_argument("--vitest", type=Path, help="vitest run --reporter=json report")
    ap.add_argument("--no-selenium", action="store_true")
    ap.add_argument("--commit", default=os.environ.get("GITHUB_SHA"))
    a = ap.parse_args(argv)

    cases: list[Case] = from_pytest(pytest_items(["tests"]), "pytest")
    missing = []
    if a.no_selenium:
        missing.append("selenium")
    else:
        cases += from_pytest(pytest_items(["tests/selenium", "--selenium"]), "selenium")
    for name, path, read in (("playwright", a.playwright, from_playwright), ("vitest", a.vitest, from_vitest)):
        if path is None:
            missing.append(name)
        else:
            cases += read(json.loads(path.read_text(encoding="utf-8")))
    data = catalog(cases, missing, a.commit)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    counts = {}
    for c in data["cases"]:
        counts[c["suite"]] = counts.get(c["suite"], 0) + 1
    print(
        f"{len(data['cases'])} cases: "
        + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        + (f"; not collected: {', '.join(missing)}" if missing else "")
    )


if __name__ == "__main__":
    main()
