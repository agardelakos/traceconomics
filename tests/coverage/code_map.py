"""The code map's back end: which tests run which module and public function, as one JSON file.

    python -I tests/coverage/code_map.py --python .coverage --src src/traceconomics --out code-map.json --commit SHA \
        [--site DIR]

Reads coverage.py's combined data file, whose lines tests/conftest.py labels `<layer>|<test>`, and
the package's source (with `ast`, nothing imported). Each line with code gets one status:

    unit, integration   a test of that layer ran it; the lowest layer wins, as on the badges
    imported            it ran only while a test file was being imported: module-level code
                        (imports, `def` and `class` lines, constants), never a test's own work
    none                nothing ran it

"Imported" is one set for the whole run, not tied to a test file: only the first file to import a
module records those lines, so which file that is depends on the order the tests run in.

Writes, for every module of the package, its counts per status, the line ranges no test runs and the
tests that run it by layer; the same for each public function, class and method (what
tests/test_docstrings.py calls public). Tests are pytest node IDs without their parameters, one
entry for a parametrized test; the wiki joins them to their cases (tests/catalog/code_map_pages.py),
so a test without a case is shown, never dropped. Stops with an error if a `repository` test ran
package code: those tests check the repository's own files, so the label would be wrong.

With `--site`, the front end too: the site's own code, from the files site/scripts/code-map-lines.mjs
writes (`lines.json`, every line with code; `layers.json`, the lines each layer's merged run ran, as
the front-end badge counts them; `bundled.json`, the lines the build put in the browser's scripts;
`vitest.json`, each Vitest file's lines and layer;
`playwright.json`, each Playwright case's; `selenium.json`, each Selenium test's, and
`selenium-run.json`, the whole suite's merged run, when that suite ran with coverage). Each line's status is the front-end badge's, from each layer's merged run:
unit or integration (Vitest), e2e (Playwright), none. Which tests run a line comes from each test's
own coverage, kept to what can be trusted, because the two ways of counting go wrong in different
places (each checked by running the code with a log line in it):
- a Vitest file alone can count the first line of a function it never calls: its lines are kept to
  its layer's merged run;
- a browser suite's merged run can drop lines its tests do run (a function the calculator page calls
  on load), while a browser test alone counts them; but it can also count a line the bundler left
  out of the browser's scripts (a function only the tests call): a browser test's lines are kept to
  the lines the build put in those scripts.
So the browser suites are compared test by test, the same way for both, and a line the badge counts
as untested can still list the browser tests that run it. Selenium is not one of the badge's layers; its lines are counted apart, with
the lines only Playwright runs and those only Selenium runs, file by file.

The same data, source and commit give the same bytes.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

LAYERS = ("unit", "integration")  # the lowest first
STATUSES = (*LAYERS, "imported", "none")
SITE_LAYERS = ("unit", "integration", "e2e")  # the front-end badge's, the lowest first
SITE_STATUSES = (*SITE_LAYERS, "none")
IMPORT = "::<import>"  # tests/conftest.py's label while a test file is imported
PARAMS = re.compile(r"\[.*\]$")


class LabelError(Exception):
    """A covered line whose label can't be right: no layer, or a repository test."""


def base(node: str) -> str:
    """A pytest node ID without its parameters: one entry per parametrized test, as in the catalog."""
    return PARAMS.sub("", node)


def ranges(lines: list[int]) -> list[list[int]]:
    """Sorted line numbers as [first, last] runs: 3, 4, 5, 9 gives [[3, 5], [9, 9]]."""
    out: list[list[int]] = []
    for n in sorted(lines):
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def members(tree: ast.Module) -> list[tuple[str, int, int]]:
    """Public functions, classes and their public methods: (name, `def` line, last line).

    The `def` or `class` line counts with the body: it runs on import, so a function that no test
    calls still has one line run, "imported", while a function of a module no test loads has none.
    Decorators are left out.
    """
    out = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and not node.name.startswith("_"):
            out.append((node.name, node.lineno, node.end_lineno))
            if isinstance(node, ast.ClassDef):
                for m in node.body:
                    if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef) and not m.name.startswith("_"):
                        out.append((f"{node.name}.{m.name}", m.lineno, m.end_lineno))
    return out


def status(contexts: list[str], where: str) -> tuple[str, dict[str, set[str]]]:
    """A line's status and the tests that ran it, by layer, from its context labels."""
    tests: dict[str, set[str]] = {k: set() for k in LAYERS}
    imported = False
    for c in contexts:
        layer, _, test = c.partition("|")
        if layer == "repository":
            raise LabelError(f"{where} ran in a repository test, which should run no package code: {test or c}")
        if test.endswith(IMPORT):
            imported = True
        elif layer in LAYERS and test:
            tests[layer].add(base(test))
        else:
            raise LabelError(f"{where} ran with a label without a layer or a test: {c!r}")
    first = next((k for k in LAYERS if tests[k]), None)
    return first or ("imported" if imported else "none"), tests


def summary(lines: dict[int, tuple[str, dict[str, set[str]]]], index: dict[str, int], wanted) -> dict:
    """Counts per status, the ranges nothing runs and the tests by layer, over the lines `wanted` keeps."""
    counts = dict.fromkeys(STATUSES, 0)
    tests: dict[str, set[str]] = {k: set() for k in LAYERS}
    ran = dict.fromkeys(LAYERS, 0)  # lines each layer runs at all, for the heatmap
    none = []
    for n, (st, by_layer) in lines.items():
        if not wanted(n):
            continue
        counts[st] += 1
        if st == "none":
            none.append(n)
        for k in LAYERS:
            tests[k] |= by_layer[k]
            ran[k] += bool(by_layer[k])
    return {
        "lines": sum(counts.values()),
        **counts,
        "no_test": ranges(none),
        "tests": {k: sorted(index[t] for t in tests[k]) for k in LAYERS},
        "ran": ran,
    }


def build(data_file: Path, src: Path, root: Path, commit: str) -> dict:
    """The map of the package under `src` from a combined coverage data file."""
    from coverage import Coverage

    cov = Coverage(data_file=str(data_file), config_file=str(root / "pyproject.toml"))
    cov.load()
    data = cov.get_data()
    measured = {}
    for f in data.measured_files():
        p = Path(f)
        measured[(p if p.is_absolute() else root / p).resolve()] = f

    per_file = {}
    all_tests: set[str] = set()
    for path in sorted(src.rglob("*.py"), key=lambda p: p.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        key = measured.get(path.resolve())
        statements = cov.analysis2(key or str(path))[1]
        by_line = data.contexts_by_lineno(key) if key else {}
        lines = {n: status(by_line.get(n, []), f"{rel}:{n}") for n in sorted(statements)}
        per_file[rel] = (path, lines)
        for _, by_layer in lines.values():
            for k in LAYERS:
                all_tests |= by_layer[k]

    tests = sorted(all_tests)
    index = {t: i for i, t in enumerate(tests)}
    modules = {}
    for rel, (path, lines) in per_file.items():
        entry = summary(lines, index, lambda n: True)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        entry["members"] = {
            name: {"line": line, **summary(lines, index, lambda n, a=line, b=last: a <= n <= b)}
            for name, line, last in members(tree)
        }
        modules[rel] = entry
    return {"schema": 1, "commit": commit, "back-end": {"tests": tests, "modules": modules}}


def site(folder: Path) -> dict:
    """The front end's part of the map, from the files site/scripts/code-map-lines.mjs wrote."""

    def read(name):
        path = folder / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    lines, merged, bundled = read("lines"), read("layers"), read("bundled")
    if lines is None or merged is None or bundled is None:
        raise FileNotFoundError(f"{folder}: no lines, layers or bundled .json to map (code-map-lines.mjs lines)")
    bundled = {f: set(ls) for f, ls in bundled.items()}
    merged = {k: {f: set(ls) for f, ls in v.items()} for k, v in merged.items()}
    vitest, playwright, selenium = read("vitest") or {}, read("playwright") or {}, read("selenium")
    # Who ran each line: {file: {line: {"unit"|"integration"|"e2e"|"selenium": {test key, …}}}}
    who: dict = {}

    def add(kind, key, by_file):
        for f, ls in by_file.items():
            browser = kind in ("e2e", "selenium")
            keep = bundled.get(f, set()) if browser else merged[kind].get(f, set())
            for n in ls:
                if n in keep:
                    who.setdefault(f, {}).setdefault(n, {}).setdefault(kind, set()).add(key)

    for test_file, v in vitest.items():
        add(v["layer"], f"vitest|{test_file}", v["lines"])
    for case, by_file in playwright.items():
        add("e2e", f"playwright|{case}", by_file)
    for node, by_file in (selenium or {}).items():
        add("selenium", f"selenium|{node}", by_file)

    keys = sorted({k for f in who.values() for n in f.values() for ks in n.values() for k in ks})
    index = {k: i for i, k in enumerate(keys)}
    kinds = (*SITE_LAYERS, "selenium")
    files = {}
    for f in sorted(lines):
        counts = dict.fromkeys(SITE_STATUSES, 0)
        ran = dict.fromkeys(kinds, 0)
        tests: dict[str, set[str]] = {k: set() for k in kinds}
        none, pw_only, sel_only = [], [], []
        for n in lines[f]:
            by = who.get(f, {}).get(n, {})
            counts[next((k for k in SITE_LAYERS if n in merged[k].get(f, ())), "none")] += 1
            for k in kinds:
                ran[k] += bool(by.get(k))
                tests[k] |= by.get(k, set())
            if not by:
                none.append(n)
            if by.get("e2e") and not by.get("selenium"):
                pw_only.append(n)
            if by.get("selenium") and not by.get("e2e"):
                sel_only.append(n)
        files[f] = {
            "lines": len(lines[f]),
            **counts,
            "no_test": ranges(none),
            "tests": {k: sorted(index[t] for t in tests[k]) for k in kinds},
            "ran": ran if selenium is not None else {**ran, "selenium": None},
            "playwright_only": ranges(pw_only) if selenium is not None else None,
            "selenium_only": ranges(sel_only) if selenium is not None else None,
        }
    return {"tests": keys, "files": files, "selenium": selenium is not None}


def write(result: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--python", required=True, type=Path, help="coverage.py data file (combined)")
    ap.add_argument("--src", required=True, type=Path, help="the package folder, e.g. src/traceconomics")
    ap.add_argument("--out", required=True, type=Path, help="the JSON file to write")
    ap.add_argument("--commit", required=True, help="the commit the coverage ran on")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="the repository root (default: here)")
    ap.add_argument("--site", type=Path, help="the folder code-map-lines.mjs wrote (site/coverage/code-map)")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{7,40}", a.commit):
        ap.error(f"--commit must be a commit hash, not {a.commit!r}")
    try:
        result = build(a.python, a.src.resolve(), a.root.resolve(), a.commit)
        if a.site is not None:
            result["front-end"] = site(a.site)
    except (LabelError, FileNotFoundError) as e:
        print(f"code map: {e}", file=sys.stderr)
        return 1
    write(result, a.out)
    m = result["back-end"]["modules"]
    totals = {s: sum(e[s] for e in m.values()) for s in STATUSES}
    print(
        f"code map: {len(m)} modules, {len(result['back-end']['tests'])} tests; lines "
        + ", ".join(f"{s} {n}" for s, n in totals.items())
    )
    if "front-end" in result:
        f = result["front-end"]["files"]
        print(
            f"code map, front end: {len(f)} files, {len(result['front-end']['tests'])} tests; lines "
            + ", ".join(f"{s} {sum(e[s] for e in f.values())}" for s in SITE_STATUSES)
            + ("" if result["front-end"]["selenium"] else "; no Selenium coverage")
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
