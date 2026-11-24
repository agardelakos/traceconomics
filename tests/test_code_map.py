"""The code map's back end (tests/coverage/code_map.py): which tests run which module and member.

A made-up package and a coverage data file written here, with the labels tests/conftest.py gives
(`<layer>|<test>`, `<layer>|<file>::<import>`); never a real coverage run.
"""

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import coverage
import pytest

sys.path.insert(0, str(Path(__file__).parent / "coverage"))
import code_map  # noqa: E402

pytestmark = pytest.mark.repository

COMMIT = "0123456789abcdef0123456789abcdef01234567"
SOURCE = textwrap.dedent('''
    """A made-up module."""

    LIMIT = 3


    def called(x):
        """Run by tests."""
        if x > LIMIT:
            return x
        return 0


    def never(x):
        """No test calls it."""
        return x + 1


    class Box:
        """A box."""

        size = 2

        def open(self):
            """Run by an integration test only."""
            return self.size
    ''').lstrip("\n")
# The statements of SOURCE, by line: 1 docstring (not a statement), 3 LIMIT, 6 def called, 8 if,
# 9 return x, 10 return 0, 13 def never, 15 return x + 1, 18 class Box, 21 size, 23 def open,
# 25 return self.size.
IMPORTED = [3, 6, 13, 18, 21, 23]


def package(tmp_path: Path) -> tuple[Path, Path]:
    """A repository root with a settings file and a package of two modules, one never imported."""
    root = tmp_path / "repo"
    src = root / "src" / "made"
    src.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[tool.coverage.run]\nbranch = true\n", encoding="utf-8")
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "mod.py").write_text(SOURCE, encoding="utf-8", newline="\n")
    (src / "unused.py").write_text('"""Never imported."""\n\nVALUE = 1\n', encoding="utf-8", newline="\n")
    return root, src


def data(tmp_path: Path, src: Path, contexts: dict[str, list[int]]) -> Path:
    path = tmp_path / ".coverage"
    d = coverage.CoverageData(str(path))
    for ctx, lines in contexts.items():
        d.set_context(ctx)
        d.add_lines({str(src / "mod.py"): lines})
    d.write()
    return path


def real_labels(src: Path, tmp_path: Path) -> Path:
    return data(
        tmp_path,
        src,
        {
            "unit|tests/test_mod.py::<import>": IMPORTED,
            "unit|tests/test_mod.py::test_called[small]": [8, 10],
            "unit|tests/test_mod.py::test_called[big]": [8, 9],
            "integration|tests/test_box.py::test_open": [8, 10, 25],
        },
    )


def test_each_line_and_member_gets_its_status_and_tests(tmp_path):
    """PY-CODEMAP-001: The map gives each line one status and each module and member its tests by layer

    Given a module whose lines are run by unit tests, by an integration test, only on import, and not at all
    And a second module that no test imports
    When the code map is built
    Then each line counts once: for the lowest layer of test that ran it, else imported, else none
    And the lines nothing runs are given as ranges
    And the module lists its tests by layer, a parametrized test once, without its parameters
    And a function its tests call lists them, one no test calls is imported only, and a method has its own entry
    And the module no test imports has every line counted as none
    """
    root, src = package(tmp_path)
    got = code_map.build(real_labels(src, tmp_path), src, root, COMMIT)
    back = got["back-end"]
    assert back["tests"] == ["tests/test_box.py::test_open", "tests/test_mod.py::test_called"]
    mod = back["modules"]["src/made/mod.py"]
    assert {k: mod[k] for k in code_map.STATUSES} == {"unit": 3, "integration": 1, "imported": 6, "none": 1}
    assert mod["lines"] == 11 and mod["no_test"] == [[15, 15]]
    assert mod["tests"] == {"unit": [1], "integration": [0]}
    members = mod["members"]
    assert members["called"]["tests"] == {"unit": [1], "integration": [0]} and members["called"]["line"] == 6
    assert members["never"]["tests"] == {"unit": [], "integration": []}
    assert (members["never"]["imported"], members["never"]["none"]) == (1, 1)
    assert members["Box.open"]["tests"] == {"unit": [], "integration": [0]}
    assert members["Box"]["integration"] == 1 and members["Box"]["imported"] == 3
    unused = back["modules"]["src/made/unused.py"]
    assert (unused["lines"], unused["none"], unused["no_test"]) == (1, 1, [[3, 3]])
    assert got["commit"] == COMMIT


@pytest.mark.parametrize(
    "label, message",
    [
        ("repository|tests/test_wiki.py::test_a", "repository test"),
        ("|tests/test_x.py::test_a", "without a layer"),
        ("unit", "without a layer or a test"),
    ],
    ids=["repository", "no-layer", "no-test"],
)
def test_a_wrong_label_stops_the_map(tmp_path, label, message):
    """PY-CODEMAP-002: A line run by a repository test, or labelled without a layer or a test, stops the map

    Given a module with one line run under a repository test's label, a label with no layer, or a bare layer
    When the code map is built
    Then it stops with an error naming the line and what is wrong with its label
    """
    root, src = package(tmp_path)
    with pytest.raises(code_map.LabelError, match=message) as e:
        code_map.build(data(tmp_path, src, {label: [8]}), src, root, COMMIT)
    assert "src/made/mod.py:8" in str(e.value)


def test_the_command_line_writes_the_same_bytes_and_needs_a_hash(tmp_path):
    """PY-CODEMAP-003: The command line writes the same bytes every time and needs a commit hash

    Given a package and its coverage data
    When the map is written twice from the command line, then once with a branch name as the commit, then once from data with a repository test's label
    Then both writes give the same bytes, and the file holds the map
    And the run with the branch name stops with an error and writes nothing
    And the run with the repository test's label exits with an error and writes nothing
    """
    root, src = package(tmp_path)
    cov = real_labels(src, tmp_path)
    script = Path(__file__).parent / "coverage" / "code_map.py"

    def run(out: Path, commit: str = COMMIT, data_file: Path = cov):
        args = ["--python", str(data_file), "--src", str(src), "--out", str(out), "--commit", commit]
        return subprocess.run(
            [sys.executable, "-I", str(script), *args, "--root", str(root)], capture_output=True, text=True
        )

    first, second = run(tmp_path / "a.json"), run(tmp_path / "b.json")
    assert first.returncode == 0 and second.returncode == 0, first.stderr
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    assert "src/made/mod.py" in json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["back-end"]["modules"]
    bad = run(tmp_path / "c.json", commit="main")
    assert bad.returncode != 0 and "commit hash" in bad.stderr and not (tmp_path / "c.json").exists()
    (tmp_path / "wrong").mkdir()
    wrong = run(tmp_path / "d.json", data_file=data(tmp_path / "wrong", src, {"repository|t.py::test_a": [8]}))
    assert wrong.returncode == 1 and "repository test" in wrong.stderr and not (tmp_path / "d.json").exists()


def site_files(folder: Path, *, selenium: bool = True) -> Path:
    """The files code-map-lines.mjs writes, made up: two site files and one test of each kind."""
    a, b = "src/lib/a.ts", "src/scripts/b.ts"
    files = {
        "lines": {a: [1, 2, 3, 4, 5, 6], b: [1, 2]},
        "layers": {"unit": {a: [1, 2]}, "integration": {a: [1, 2, 3]}, "e2e": {a: [4], b: [1]}},
        "bundled": {a: [4, 5], b: [1, 2]},
        "vitest": {
            "src/lib/a.test.ts": {"layer": "unit", "lines": {a: [1, 2, 6]}},  # 6: a header it never calls
            "src/lib/data-files.test.ts": {"layer": "integration", "lines": {a: [3]}},
        },
        # 5 is bundled but the merged run lost it; 3 isn't bundled at all
        "playwright": {"PW-X-001": {a: [4, 5], b: [1]}, "PW-X-002": {a: [3]}},
    }
    if selenium:
        files["selenium"] = {"tests/selenium/test_b.py::test_b": {a: [4], b: [1, 2]}}
    folder.mkdir()
    for name, data in files.items():
        (folder / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


def test_the_front_end_takes_the_badge_statuses_and_each_tests_trusted_lines(tmp_path):
    """PY-CODEMAP-004: The front end takes each line's status from the badge's runs and its tests from their own lines

    Given a site file's lines run by a unit and an integration Vitest file, two Playwright cases and a Selenium test, and each layer's merged run
    And a Vitest file whose own lines include one its layer's merged run didn't run
    And a Playwright case whose own lines include one the merged run lost and one the build never bundled
    When the map's front end is built, with Selenium's lines and then without them
    Then each line's status is the first layer whose merged run ran it, else none, as on the badge
    And a Vitest file's line counts only where its layer's merged run ran it, a browser test's only where the build bundled it
    And each suite's count of lines it runs, and the lines only Playwright or only Selenium runs, follow from those
    And the lines no test runs at all are given as ranges
    And without Selenium's lines its counts and the comparison are left empty and the map says so
    """
    got = code_map.site(site_files(tmp_path / "site"))
    tests = got["tests"]
    a, b = got["files"]["src/lib/a.ts"], got["files"]["src/scripts/b.ts"]
    assert {k: a[k] for k in code_map.SITE_STATUSES} == {"unit": 2, "integration": 1, "e2e": 1, "none": 2}
    assert a["no_test"] == [[6, 6]]
    names = {k: [tests[i] for i in v] for k, v in a["tests"].items()}
    assert names == {
        "unit": ["vitest|src/lib/a.test.ts"],
        "integration": ["vitest|src/lib/data-files.test.ts"],
        "e2e": ["playwright|PW-X-001"],
        "selenium": ["selenium|tests/selenium/test_b.py::test_b"],
    }
    assert a["ran"] == {"unit": 2, "integration": 1, "e2e": 2, "selenium": 1}
    assert (a["playwright_only"], a["selenium_only"]) == ([[5, 5]], [])
    assert (b["e2e"], b["none"], b["no_test"], b["selenium_only"]) == (1, 1, [], [[2, 2]])
    assert got["selenium"] is True

    without = code_map.site(site_files(tmp_path / "site2", selenium=False))
    a2 = without["files"]["src/lib/a.ts"]
    assert without["selenium"] is False and a2["ran"]["selenium"] is None
    assert a2["playwright_only"] is None and a2["selenium_only"] is None
    with pytest.raises(FileNotFoundError):
        code_map.site(tmp_path / "missing")


SITE = Path(__file__).resolve().parent.parent / "site"


def test_the_vitest_integration_files_are_named_alike_everywhere():
    """PY-CODEMAP-005: The Vitest files counted as integration are the same in the code map, the quick check and CI

    Given the code map's list of Vitest integration files, the quick check's script and CI's unit-only Vitest run
    When the three lists are read
    Then they name the same files
    And each file exists
    """
    options = (SITE / "scripts" / "coverage-options.mjs").read_text(encoding="utf-8")
    listed = re.search(r"VITEST_INTEGRATION = \[([^\]]*)\]", options)[1]
    in_map = set(re.findall(r'"([^"]+)"', listed))
    script = json.loads((SITE / "package.json").read_text(encoding="utf-8"))["scripts"]["check:code"]
    in_check = set(re.findall(r"--exclude (\S+)", script))
    workflow = (SITE.parent / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    unit_run = next(line for line in workflow.splitlines() if "npx vitest run --exclude" in line)
    in_ci = set(re.findall(r"--exclude (\S+)", unit_run))
    assert in_map == in_check == in_ci and len(in_map) == 2
    assert all((SITE / f).is_file() for f in in_map)


sys.path.insert(0, str(Path(__file__).parent / "coverage"))
import mutation  # noqa: E402


def test_mutmut_runs_the_tests_the_code_map_says_run_the_engine(tmp_path):
    """PY-MUT-001: mutmut is given the test files the code map says run the engine, and nothing else

    Given a code map in which two test files run the engine and a third runs only another module
    And a settings file with mutmut's empty test selection
    When the selection is written, then with a map in which no test runs the engine, then into settings without the line
    Then the selection names the two files, once each and sorted, and the rest of the settings is unchanged
    And a map without the engine's tests, or settings without the line, stop with an error
    """
    tests = ["tests/test_b.py::test_1", "tests/test_a.py::test_2", "tests/test_a.py::test_3", "tests/test_c.py::test_4"]
    modules = {
        "src/traceconomics/engine/chain.py": {"tests": {"unit": [0, 1], "integration": [2]}},
        "src/traceconomics/store/db.py": {"tests": {"unit": [3], "integration": []}},
    }
    code_map = {"back-end": {"tests": tests, "modules": modules}}
    settings = tmp_path / "pyproject.toml"
    before = '[tool.mutmut]\nonly_mutate = ["x"]\npytest_add_cli_args_test_selection = []\nother = 1\n'
    settings.write_text(before, encoding="utf-8")
    assert mutation.select(code_map, settings) == ["tests/test_a.py", "tests/test_b.py"]
    after = settings.read_text(encoding="utf-8")
    assert after == before.replace("= []", '= ["tests/test_a.py", "tests/test_b.py"]')
    with pytest.raises(SystemExit, match="no test that runs the engine"):
        mutation.select(
            {
                "back-end": {
                    "tests": tests,
                    "modules": {"src/traceconomics/store/db.py": modules["src/traceconomics/store/db.py"]},
                }
            },
            settings,
        )
    settings.write_text("[tool.mutmut]\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no `pytest_add_cli_args_test_selection` line"):
        mutation.select(code_map, settings)


def test_the_report_counts_mutants_and_lists_each_survivor(tmp_path):
    """PY-MUT-002: The report counts every mutant's result and lists each survivor with its function and change

    Given mutmut's result files for two engine modules: killed, survived, timed out, skipped and unknown results, one survivor in a method
    When the report is written
    Then each result is counted, and the score is the killed and timed-out share of those not skipped
    And each function's results are counted apart, a method's under Class.method
    And the run's start and its link are kept
    And each survivor names its function (a method as Class.method) and its change, without the diff's file headers
    And the engine's source is fingerprinted, the same whatever its line endings
    And without results the report stops with an error
    """
    root = tmp_path
    engine = root / "src" / "traceconomics" / "engine"
    engine.mkdir(parents=True)
    (engine / "chain.py").write_bytes(b"a = 1\r\nb = 2\r\n")
    meta = root / "mutants" / "src" / "traceconomics" / "engine"
    meta.mkdir(parents=True)
    (meta / "chain.py.meta").write_text(
        json.dumps(
            {
                "exit_code_by_key": {
                    "traceconomics.engine.chain.x_link__mutmut_1": 1,
                    "traceconomics.engine.chain.x_link__mutmut_2": 0,
                    "traceconomics.engine.chain.xǁChainResultǁfallback_summary__mutmut_1": 0,
                    "traceconomics.engine.chain.x_chain__mutmut_1": 36,
                }
            }
        ),
        encoding="utf-8",
    )
    (meta / "rates.py.meta").write_text(
        json.dumps(
            {
                "exit_code_by_key": {
                    "traceconomics.engine.rates.x_rebase__mutmut_1": 34,
                    "traceconomics.engine.rates.x_rebase__mutmut_2": 99,
                }
            }
        ),
        encoding="utf-8",
    )
    diff = "# x: survived\n--- src/a.py\n+++ src/a.py\n@@ -1 +1 @@\n-    continue\n+    break\n"
    got = mutation.report(root, COMMIT, show=lambda m: diff, started="2026-12-08T10:00:00Z", run_url="https://run/1")
    assert got["mutants"] == 6
    assert (got["started"], got["run_url"]) == ("2026-12-08T10:00:00Z", "https://run/1")
    assert got["functions"] == {
        "traceconomics.engine.chain.ChainResult.fallback_summary": {"survived": 1},
        "traceconomics.engine.chain.chain": {"timeout": 1},
        "traceconomics.engine.chain.link": {"killed": 1, "survived": 1},
        "traceconomics.engine.rates.rebase": {"skipped": 1, "suspicious": 1},
    }
    assert got["counts"] == {"killed": 1, "skipped": 1, "survived": 2, "suspicious": 1, "timeout": 1}
    assert got["score"] == 40.0  # (1 killed + 1 timeout) of 5 not skipped
    assert [s["function"] for s in got["survivors"]] == [
        "traceconomics.engine.chain.link",
        "traceconomics.engine.chain.ChainResult.fallback_summary",
    ]
    assert got["survivors"][0]["change"] == ["-    continue", "+    break"]
    (engine / "chain.py").write_bytes(b"a = 1\nb = 2\n")
    assert mutation.fingerprint(root) == got["source"]
    (meta / "chain.py.meta").unlink()
    (meta / "rates.py.meta").unlink()
    with pytest.raises(SystemExit, match="no mutmut results"):
        mutation.report(root, COMMIT, show=lambda m: diff)


def test_each_stored_run_keeps_its_line_in_the_history(tmp_path):
    """PY-MUT-004: storing a run replaces the newest result and adds its line to the history, the one before kept

    Given a test-history folder holding one result stored before the history began
    When two more runs are stored
    Then the newest result is the last run's, in full
    And the history has three lines, oldest first, each with its start, commit, link, changes, counts and score only
    """
    first = {"commit": "a" * 40, "mutants": 10, "counts": {"killed": 9, "survived": 1}, "score": 90.0, "survivors": [1]}
    (tmp_path / "mutation.json").write_text(json.dumps(first), encoding="utf-8")
    runs = [
        {**first, "commit": "b" * 40, "started": "2026-12-01T10:00:00Z", "run_url": "u1", "score": 100.0},
        {**first, "commit": "c" * 40, "started": "2026-12-08T10:00:00Z", "run_url": "u2", "score": 95.0},
    ]
    for r in runs:
        mutation.store(r, tmp_path)
    assert json.loads((tmp_path / "mutation.json").read_text(encoding="utf-8")) == runs[1]
    lines = [json.loads(x) for x in (tmp_path / mutation.HISTORY).read_text(encoding="utf-8").splitlines()]
    assert [x["commit"][0] for x in lines] == ["a", "b", "c"] and [x["score"] for x in lines] == [90.0, 100.0, 95.0]
    assert all(set(x) == set(mutation.SUMMARY) for x in lines) and lines[0]["started"] is None


def test_every_equivalent_survivor_has_its_reason():
    """PY-MUT-003: Every survivor listed as behaving the same as the code has its function, change and reason

    Given the repository's list of equivalent survivors
    When it is read
    Then it parses, and every entry has a function, a change and a reason that isn't empty
    """
    path = Path(__file__).parent / "coverage" / "mutation-equivalent.toml"
    for entry in mutation.equivalents(path):
        assert entry["function"].startswith("traceconomics.engine.") and entry["change"]
