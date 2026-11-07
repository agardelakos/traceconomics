"""The coverage split by layer: the layer marks every test carries (tests/conftest.py) and the
badges' arithmetic and drawing (tests/coverage/overview.py)."""

import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import coverage
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "coverage"))
import overview  # noqa: E402

pytestmark = pytest.mark.repository


def test_parts_add_up_to_the_rounded_down_total():
    """PY-COV-001: each badge's parts add up to its total, which is rounded down

    Given 7 lines with code, 2 covered by each of unit, integration and e2e tests
    When the total is split
    Then the total is 85.7%, rounded down from 85.71%
    And the three parts add up to it exactly
    And the tenths left by rounding each part down go to the lower layers first on a tie
    """
    total, parts = overview.split(7, {"unit": 2, "integration": 2, "e2e": 2})
    assert total == 857
    assert sum(parts.values()) == total
    assert parts == {"unit": 286, "integration": 286, "e2e": 285}


def test_split_edge_cases():
    """PY-COV-002: a split with nothing to count, nothing covered or everything covered

    Given no lines with code, then lines none of which are covered, then lines all covered by one layer
    When each is split
    Then the first two give 0% in total and in every part
    And the last gives 100% to that layer alone
    """
    assert overview.split(0, {"unit": 0, "integration": 0}) == (0, {"unit": 0, "integration": 0})
    assert overview.split(9, {"unit": 0, "integration": 0}) == (0, {"unit": 0, "integration": 0})
    assert overview.split(9, {"unit": 0, "integration": 9}) == (1000, {"unit": 0, "integration": 1000})


def test_a_line_counts_for_the_lowest_layer_that_ran_it():
    """PY-COV-003: a line run by several layers counts once, for the lowest

    Given lines run by unit and integration tests, by integration and e2e tests, by e2e tests alone, and by none
    When each line's layer is chosen
    Then they count for unit, integration and e2e, and the last for none
    """
    layers = ("unit", "integration", "e2e")
    assert overview.assign({"integration", "unit"}, layers) == "unit"
    assert overview.assign({"e2e", "integration"}, layers) == "integration"
    assert overview.assign({"e2e"}, layers) == "e2e"
    assert overview.assign(set(), layers) is None


def write_data(tmp_path: Path, contexts: dict[str, list[int]]) -> tuple[Path, Path]:
    """A source file of five statements and a coverage data file with lines under each context."""
    src = tmp_path / "mod.py"
    src.write_text("a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n", encoding="utf-8", newline="\n")
    data = coverage.CoverageData(str(tmp_path / ".coverage"))
    for ctx, lines in contexts.items():
        data.set_context(ctx)
        data.add_lines({str(src): lines})
    data.write()
    return tmp_path / ".coverage", src


def test_back_end_lines_per_layer_from_the_data_file(tmp_path):
    """PY-COV-004: the back-end split is read from coverage.py's contexts

    Given a file of five statements, two run by unit tests, three by integration tests, one of them also by a unit test
    When the back-end split is read from the coverage data file
    Then the file has five lines with code, two for unit and two for integration
    And no problem is reported
    """
    data_file, src = write_data(tmp_path, {"unit": [1, 2], "integration": [2, 3, 4]})
    got = overview.back_end(data_file)
    assert got["files"][src.as_posix()] == {"total": 5, "unit": 2, "integration": 2}
    assert got["problems"] == []


def test_back_end_refuses_wrong_labels(tmp_path):
    """PY-COV-005: a covered line without a layer, or run by a repository test, is a problem

    Given a line run with no context and a line run by a repository test
    When the back-end split is read
    Then both lines are reported as problems
    And neither counts for a layer
    """
    data_file, src = write_data(tmp_path, {"": [1], "repository": [2]})
    got = overview.back_end(data_file)
    assert got["files"][src.as_posix()] == {"total": 5, "unit": 0, "integration": 0}
    assert len(got["problems"]) == 2
    assert any("no layer" in p for p in got["problems"])
    assert any("repository test" in p for p in got["problems"])


def test_badge_shows_total_and_parts_and_nothing_else():
    """PY-COV-006: a badge shows its total and each layer's part, self-contained

    Given a front-end result of 92.4% split into unit, integration and e2e parts
    When its badge is drawn
    Then the SVG parses, with one segment for the label, one for the total and one per layer
    And its title gives the total, each part and the rule for lines run by several layers
    And it has no script and refers to no other file or site
    """
    result = {"lines": 1000, "covered": 924, "pct": 92.4,
              "layers": {"unit": {"lines": 600, "pct": 60.0}, "integration": {"lines": 50, "pct": 5.0},
                         "e2e": {"lines": 274, "pct": 27.4}}}
    svg = overview.badge("front-end", result, "fair")
    root = ET.fromstring(svg)
    ns = {"s": "http://www.w3.org/2000/svg"}
    texts = [t.text for t in root.iterfind(".//s:g/s:text", ns)]
    assert texts == ["front-end coverage", "92.4%", "unit 60.0%", "integration 5.0%", "e2e 27.4%"]
    title = root.find("s:title", ns).text
    for part in ("92.4%", "unit tests 60.0%", "integration tests 5.0%", "end-to-end tests in a browser 27.4%",
                 "counts once"):
        assert part in title
    assert "<script" not in svg and "href" not in svg and "http" not in svg.replace(ns["s"], "")


def test_back_end_standing_has_the_sites_bounds():
    """PY-COV-009: the back-end total is coloured with the site's bounds

    Given back-end totals just below 90%, at 90%, just below 95% and at 95%
    When each total's standing is read
    Then they are low, fair, fair and good
    And the ratchet the run fails below is no higher than the 90% aim
    """
    assert [overview.standing(v) for v in (89.9, 90.0, 94.9, 95.0)] == ["low", "fair", "fair", "good"]
    assert overview.RATCHET <= overview.FLOOR


def site_summary(path: Path) -> Path:
    path.write_text(json.dumps({"standing": "good", "layers": {
        "files": {"src/lib/a.ts": {"total": 2, "unit": 1, "integration": 0, "e2e": 1}}, "problems": []}}),
        encoding="utf-8", newline="\n")
    return path


def test_strict_run_fails_below_the_ratchet(tmp_path):
    """PY-COV-010: with --strict, a back-end total below the ratchet fails the run

    Given a back-end with 3 of 5 lines covered (60%), below the ratchet
    And the same back-end with all 5 covered
    When the split is run with --strict, and the first also without it
    Then the 60% run fails with --strict and passes without it, its badge drawn either way
    And the fully covered run passes with --strict
    """
    assert overview.RATCHET > 60
    site = site_summary(tmp_path / "summary.json")
    low = tmp_path / "low"
    low.mkdir()
    data_file, _ = write_data(low, {"unit": [1, 2, 3]})
    args = ["--python", str(data_file), "--site", str(site), "--out", str(low / "out")]
    assert overview.main([*args, "--strict"]) == 1
    assert overview.main(args) == 0
    assert (low / "out" / "coverage-back-end.svg").is_file()
    full = tmp_path / "full"
    full.mkdir()
    data_file, _ = write_data(full, {"unit": [1, 2, 3, 4, 5]})
    assert overview.main(["--python", str(data_file), "--site", str(site), "--out", str(full / "out"),
                          "--strict"]) == 0


def run_pytest(project: Path, *args: str) -> subprocess.CompletedProcess:
    # A run of its own, on a throwaway project with a copy of the real conftest. COVERAGE_FILE is
    # set so a measured CI run never shares its data file with this inner one.
    env = dict(os.environ, COVERAGE_FILE=str(project / ".coverage"))
    return subprocess.run([sys.executable, "-I", *args], cwd=project, env=env, capture_output=True, text=True)


def project(tmp_path: Path, tests: dict[str, str]) -> Path:
    shutil.copy(HERE / "conftest.py", tmp_path / "conftest.py")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\nmarkers = ["unit: u", "integration: i", "repository: r"]\n'
        '[tool.coverage.run]\ncore = "ctrace"\nsource = ["."]\nomit = ["conftest.py", "test_*.py"]\n',
        encoding="utf-8", newline="\n")
    (tmp_path / "lib.py").write_text(
        "def low():\n    return 1\n\n\ndef high():\n    return 2\n", encoding="utf-8", newline="\n")
    for name, body in tests.items():
        (tmp_path / name).write_text(body, encoding="utf-8", newline="\n")
    return tmp_path


def test_a_test_file_without_a_layer_stops_the_run(tmp_path):
    """PY-COV-007: a test file that names no layer stops the run before any test

    Given a test file with no `pytestmark` layer next to one that has it
    When pytest runs
    Then it stops with a usage error naming the file without a layer
    And no test runs
    """
    p = project(tmp_path, {
        "test_marked.py": "import pytest\n\npytestmark = pytest.mark.unit\n\n\ndef test_a():\n    pass\n",
        "test_bare.py": "def test_b():\n    pass\n",
    })
    done = run_pytest(p, "-m", "pytest", "-p", "no:cacheprovider")
    assert done.returncode == pytest.ExitCode.USAGE_ERROR, done.stdout + done.stderr
    assert "test_bare.py" in done.stderr and "test_marked.py" not in done.stderr
    assert "passed" not in done.stdout


def test_each_line_is_labelled_with_the_layer_that_ran_it(tmp_path):
    """PY-COV-008: coverage records the layer of the test that ran each line

    Given a unit test file calling one function and an integration test in it, marked to override its file, calling another
    When the tests run under coverage
    Then the first function's body is recorded under unit and the second's under integration
    And the module-level lines, run when the file is imported, are recorded under the file's layer
    """
    p = project(tmp_path, {
        "test_lib.py": ("import pytest\n\nimport lib\n\npytestmark = pytest.mark.unit\n\n\n"
                        "def test_low():\n    assert lib.low() == 1\n\n\n"
                        "@pytest.mark.integration\ndef test_high():\n    assert lib.high() == 2\n"),
    })
    done = run_pytest(p, "-m", "coverage", "run", "-m", "pytest", "-p", "no:cacheprovider")
    assert done.returncode == 0, done.stdout + done.stderr
    data = coverage.CoverageData(str(p / ".coverage"))
    data.read()
    by_line = data.contexts_by_lineno(str(p / "lib.py"))
    assert set(by_line[2]) == {"unit"}              # low()'s body
    assert set(by_line[6]) == {"integration"}       # high()'s body
    assert set(by_line[1]) == {"unit"} and set(by_line[5]) == {"unit"}   # the defs, run on import
