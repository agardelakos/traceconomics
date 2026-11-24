"""The code map's back end (tests/coverage/code_map.py): which tests run which module and member.

A made-up package and a coverage data file written here, with the labels tests/conftest.py gives
(`<layer>|<test>`, `<layer>|<file>::<import>`); never a real coverage run.
"""

import json
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
