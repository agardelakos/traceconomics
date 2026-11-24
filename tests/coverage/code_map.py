"""The code map's back end: which tests run which module and public function, as one JSON file.

    python -I tests/coverage/code_map.py --python .coverage --src src/traceconomics --out code-map.json --commit SHA

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
entry for a parametrized test; the wiki joins them to their cases (tests/catalog/code_reference.py),
so a test without a case is shown, never dropped. Stops with an error if a `repository` test ran
package code: those tests check the repository's own files, so the label would be wrong.

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
    none = []
    for n, (st, by_layer) in lines.items():
        if not wanted(n):
            continue
        counts[st] += 1
        if st == "none":
            none.append(n)
        for k in LAYERS:
            tests[k] |= by_layer[k]
    return {
        "lines": sum(counts.values()),
        **counts,
        "no_test": ranges(none),
        "tests": {k: sorted(index[t] for t in tests[k]) for k in LAYERS},
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
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{7,40}", a.commit):
        ap.error(f"--commit must be a commit hash, not {a.commit!r}")
    try:
        result = build(a.python, a.src.resolve(), a.root.resolve(), a.commit)
    except LabelError as e:
        print(f"code map: {e}", file=sys.stderr)
        return 1
    write(result, a.out)
    m = result["back-end"]["modules"]
    totals = {s: sum(e[s] for e in m.values()) for s in STATUSES}
    print(
        f"code map: {len(m)} modules, {len(result['back-end']['tests'])} tests; lines "
        + ", ".join(f"{s} {n}" for s, n in totals.items())
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
