"""Mutation testing of the engine: which tests mutmut runs, and what its run found, for the wiki.

    python -I tests/coverage/mutation.py select --map code-map.json [--pyproject pyproject.toml]
    mutmut run
    python -I tests/coverage/mutation.py report --out mutation.json --commit SHA

mutmut (the `mutation` extra; settings in pyproject.toml, `[tool.mutmut]`) makes small changes to
src/traceconomics/engine, one at a time (a `<` for a `<=`, a `break` for a `continue`), and runs the
tests on each. A change some test notices is "killed"; one no test notices "survived": either the
tests miss something, or the change behaves the same as the code (an equivalent mutant). Coverage
says which lines a test runs; this says whether the tests would notice those lines going wrong.

`select` writes the test files the code map (tests/coverage/code_map.py) says run the engine into
`pytest_add_cli_args_test_selection`, so mutmut runs only those: the others read files mutmut's copy
of the repository doesn't have, and couldn't notice a change to the engine anyway.

`report` reads mutmut's results (mutants/**/*.meta) and each survivor's change (`mutmut show`), and
writes the counts, the score (killed or timed out, of those tested, as mutmut counts it), each
survivor with its function and change, and a fingerprint of the engine's source, so the wiki can say
when the engine has changed since. Survivors that behave the same as the code are listed, with the
reason, in tests/coverage/mutation-equivalent.toml; the wiki shows the reason beside them.

Standard library only (mutmut is called as a command).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path

ENGINE = "src/traceconomics/engine/"
SELECTION = re.compile(r"^pytest_add_cli_args_test_selection = .*$", re.M)
# mutmut's exit codes, as its own `mutmut.stats.status_by_exit_code` reads them (3.8.1).
STATUS = {
    1: "killed",
    3: "killed",
    0: "survived",
    5: "no tests",
    33: "no tests",
    34: "skipped",
    36: "timeout",
    24: "timeout",
    -24: "timeout",
    152: "timeout",
    255: "timeout",
    37: "caught by type check",
    None: "not checked",
}


def engine_tests(code_map: dict) -> list[str]:
    """The test files whose tests run some line of the engine, from the code map's back end."""
    back = code_map["back-end"]
    files = set()
    for path, entry in back["modules"].items():
        if path.startswith(ENGINE):
            for layer in entry["tests"].values():
                files |= {back["tests"][i].split("::", 1)[0] for i in layer}
    return sorted(files)


def select(code_map: dict, pyproject: Path) -> list[str]:
    """Write the engine's test files into pyproject.toml's mutmut settings; return them."""
    files = engine_tests(code_map)
    if not files:
        raise SystemExit("the code map names no test that runs the engine")
    text = pyproject.read_text(encoding="utf-8")
    if not SELECTION.search(text):
        raise SystemExit(f"{pyproject}: no `pytest_add_cli_args_test_selection` line in [tool.mutmut]")
    pyproject.write_text(
        SELECTION.sub(lambda _: "pytest_add_cli_args_test_selection = " + json.dumps(files), text, count=1),
        encoding="utf-8",
        newline="\n",
    )
    return files


def status(exit_code) -> str:
    """A mutant's result from mutmut's exit code; an unknown code is suspicious, as mutmut says."""
    return STATUS.get(exit_code, "suspicious")


def function_of(mutant: str) -> str:
    """The function a mutant changes: `traceconomics.engine.chain.x_link__mutmut_3` is
    `traceconomics.engine.chain.link`; a method, `...xǁChainResultǁfallback_summary__mutmut_1`, is
    `...ChainResult.fallback_summary`."""
    name = mutant.rsplit("__mutmut_", 1)[0]
    module, _, local = name.rpartition(".")
    local = local.removeprefix("x_") if local.startswith("x_") else local.removeprefix("xǁ")
    return f"{module}.{local.replace('ǁ', '.')}"


def change(diff: str) -> list[str]:
    """A survivor's change: the removed and added lines of its diff, without the file headers."""
    return [line.rstrip() for line in diff.splitlines() if line[:1] in "+-" and not line.startswith(("+++", "---"))]


def results(mutants: Path) -> dict[str, str]:
    """Every mutant's result, from mutmut's files in `mutants`."""
    out = {}
    for meta in sorted(mutants.rglob("*.py.meta")):
        data = json.loads(meta.read_text(encoding="utf-8"))
        for name, code in data.get("exit_code_by_key", {}).items():
            out[name] = status(code)
    return out


def fingerprint(root: Path) -> dict[str, str]:
    """Each engine file's SHA-256 (line endings made LF), so a later reader can tell if it changed."""
    out = {}
    for path in sorted((root / ENGINE).rglob("*.py")):
        data = path.read_bytes().replace(b"\r\n", b"\n")
        out[path.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
    return out


def show(mutant: str) -> str:
    """mutmut's diff for one mutant."""
    done = subprocess.run(["mutmut", "show", mutant], capture_output=True, text=True, check=True)
    return done.stdout


def report(root: Path, commit: str, show=show) -> dict:
    """The run's result: counts, score, survivors with their changes, and the engine's fingerprint."""
    found = results(root / "mutants")
    if not found:
        raise SystemExit("no mutmut results in mutants/ (run `mutmut run` first)")
    counts = Counter(found.values())
    tested = len(found) - counts["skipped"]
    caught = counts["killed"] + counts["timeout"] + counts["caught by type check"]
    survivors = [
        {"mutant": m, "function": function_of(m), "change": change(show(m))}
        for m in sorted(found)
        if found[m] == "survived"
    ]
    return {
        "schema": 1,
        "commit": commit,
        "mutants": len(found),
        "counts": dict(sorted(counts.items())),
        "score": round(100 * caught / tested, 1) if tested else None,
        "survivors": survivors,
        "source": fingerprint(root),
    }


def equivalents(path: Path) -> list[dict]:
    """The survivors that behave the same as the code, each with its function, change and reason."""
    if not path.is_file():
        return []
    entries = tomllib.loads(path.read_text(encoding="utf-8")).get("equivalent", [])
    for e in entries:
        missing = {"function", "change", "reason"} - set(e)
        if missing or not str(e.get("reason", "")).strip():
            raise ValueError(f"{path}: an entry needs a function, a change and a reason: {e}")
    return entries


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("select", help="write the engine's tests into [tool.mutmut]")
    s.add_argument("--map", required=True, type=Path, help="code-map.json")
    s.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    r = sub.add_parser("report", help="mutmut's results as mutation.json")
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--commit", required=True, help="the commit mutmut ran on")
    r.add_argument("--root", type=Path, default=Path.cwd())
    a = ap.parse_args(argv)
    if a.command == "select":
        files = select(json.loads(a.map.read_text(encoding="utf-8")), a.pyproject)
        print(f"mutmut will run {len(files)} test files: " + ", ".join(files))
        return 0
    if not re.fullmatch(r"[0-9a-f]{7,40}", a.commit):
        ap.error(f"--commit must be a commit hash, not {a.commit!r}")
    result = report(a.root, a.commit)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(
        json.dumps(result, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"mutation: {result['mutants']} mutants, score {result['score']}%, "
        + ", ".join(f"{k} {v}" for k, v in result["counts"].items())
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
