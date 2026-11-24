"""The wiki's code reference (tests/catalog/code_reference.py): its pages, its Markdown and its limits.

Most tests run the generator on a small made-up package written here; two run it on the real one,
because what they guard (identical bytes, nothing private) is about the real docstrings.
"""

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "catalog"))
import code_reference  # noqa: E402

pytestmark = pytest.mark.repository

ROOT = Path(__file__).resolve().parent.parent
REPO = "owner/name"
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def made_up(tmp_path: Path) -> Path:
    """A package with a top-level module, a subpackage, private parts and a docstring with a code block."""
    src = tmp_path / "src" / "traceconomics"
    files = {
        "__init__.py": '"""The package."""\n',
        "job.py": '''
            """The daily job.

            It runs once a day.
            """


            def run(config, *, force=False):
                """One run of the job."""


            def _helper():
                """Private, never listed."""


            class Lock:
                """A lock file."""

                def take(self, wait=0):
                    """Take the lock."""

                def _private(self):
                    """Private, never listed."""
            ''',
        "engine/__init__.py": '"""The engine: arithmetic only."""\n',
        "engine/chain.py": '''
            """Chain-linking.

            The formula, with weights w_i and prices P_i:

                I(y, m) = I(Dec y-1) * link(y, m)

            Prices on any base: <only ratios> are used, and `a_b * c` is code.
            - a list item
              - nested
            - a list item that wraps
                 deeper, still text
            """


            def link(weights, prices):
                """One month's link."""


            def spare():
                """Never called."""


            class Point:
                """A point."""

                x: int = 0
            ''',
    }
    for name, text in files.items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return src


def generate(tmp_path: Path) -> Path:
    out = tmp_path / "wiki"
    code_reference.generate(made_up(tmp_path), out, REPO, COMMIT)
    return out


def test_one_page_per_package_with_public_members_linked_to_the_commit(tmp_path):
    """PY-CODEREF-001: The code reference has a page per package, listing public members linked to their source line

    Given a made-up package with a top-level module, a subpackage and private functions and methods
    When the code reference is generated
    Then it writes the overview and one page for the top-level modules and one per subpackage
    And each page lists every public function, class and method with its arguments and first line
    And nothing with a leading underscore is listed
    And every source link points at the given commit and the member's line
    """
    out = generate(tmp_path)
    assert sorted(p.name for p in out.glob("Code*.md")) == ["Code-engine.md", "Code-top-level.md", "Code.md"]
    top = (out / "Code-top-level.md").read_text(encoding="utf-8")
    assert "`run(config, *, force)`" in top and "One run of the job." in top
    assert "class `Lock`" in top and "`take(wait)`" in top and "Take the lock." in top
    assert "_helper" not in top and "_private" not in top
    assert f"https://github.com/{REPO}/blob/{COMMIT}/src/traceconomics/job.py#L7)" in top  # `def run` is line 7
    assert f"https://github.com/{REPO}/commit/{COMMIT}" in top
    overview = (out / "Code.md").read_text(encoding="utf-8")
    assert "[`traceconomics.engine`](Code-engine)" in overview and "The engine: arithmetic only." in overview


def test_docstrings_become_markdown_with_code_blocks_kept_exactly(tmp_path):
    """PY-CODEREF-002: Docstrings become Markdown: indented blocks stay exact code, other text is escaped

    Given a module docstring with an indented formula, angle brackets, underscores, a code span, a nested list and a deeply wrapped list item
    When its page is generated
    Then the formula is a fenced code block, character for character
    And outside code, angle brackets, underscores and asterisks are escaped so Markdown shows them as written
    And the code span is left as it is
    And the list keeps its nesting
    And a list item's continuation line, however deep, stays text
    """
    page = (generate(tmp_path) / "Code-engine.md").read_text(encoding="utf-8")
    assert "```text\nI(y, m) = I(Dec y-1) * link(y, m)\n```" in page
    assert "weights w\\_i and prices P\\_i" in page
    assert "&lt;only ratios&gt;" in page
    assert "`a_b * c` is code" in page
    assert "- a list item\n  - nested" in page
    assert "- a list item that wraps\n  deeper, still text" in page


def test_the_sidebar_block_is_replaced_and_the_rest_kept(tmp_path):
    """PY-CODEREF-003: The code reference updates only its own block of the sidebar

    Given a sidebar with hand-written items, the code block's markers and the test pages' block
    When the code reference is generated twice
    Then the code block lists the overview and every package page
    And everything outside the code block is unchanged
    And the second run changes nothing
    """
    out = tmp_path / "wiki"
    out.mkdir()
    before = (
        "- [Home](Home)\n  <!-- code:start -->\n  <!-- code:end -->\n\n"
        "- [Tests](Tests)\n  <!-- generated:start -->\n  <!-- generated:end -->\n"
    )
    (out / "_Sidebar.md").write_text(before, encoding="utf-8")
    src = made_up(tmp_path)
    code_reference.generate(src, out, REPO, COMMIT)
    first = (out / "_Sidebar.md").read_text(encoding="utf-8")
    assert "- [Code reference](Code)\n  - [Top-level modules](Code-top-level)\n  - [engine](Code-engine)" in first
    outside = re.sub(r"<!-- code:start -->.*?<!-- code:end -->", "", first, flags=re.S)
    assert outside == re.sub(r"<!-- code:start -->.*?<!-- code:end -->", "", before, flags=re.S)
    code_reference.generate(src, out, REPO, COMMIT)
    assert (out / "_Sidebar.md").read_text(encoding="utf-8") == first


def test_pages_of_removed_packages_go_and_other_pages_stay(tmp_path):
    """PY-CODEREF-004: A page for a package that no longer exists is removed; other wiki pages stay

    Given a wiki folder with a code page for a removed package, a test page and a hand-written page
    When the code reference is generated
    Then the removed package's page is gone
    And the test page and the hand-written page are untouched
    """
    out = tmp_path / "wiki"
    out.mkdir()
    for name in ("Code-gone.md", "Tests-pytest.md", "Home.md"):
        (out / name).write_text("kept?\n", encoding="utf-8")
    code_reference.generate(made_up(tmp_path), out, REPO, COMMIT)
    assert not (out / "Code-gone.md").exists()
    assert (out / "Tests-pytest.md").read_text(encoding="utf-8") == "kept?\n"
    assert (out / "Home.md").read_text(encoding="utf-8") == "kept?\n"


def pages(out: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(out.glob("*.md"))}


def test_the_real_package_gives_the_same_bytes_every_time(tmp_path):
    """PY-CODEREF-005: The code reference of the real package is byte-identical from run to run

    Given the package's source and one commit
    When the code reference is generated twice into separate folders
    Then both runs write the same files, byte for byte
    And there is a page for every package folder and one for the top-level modules
    """
    src = ROOT / "src" / "traceconomics"
    code_reference.generate(src, tmp_path / "a", REPO, COMMIT, ROOT)
    code_reference.generate(src, tmp_path / "b", REPO, COMMIT, ROOT)
    assert pages(tmp_path / "a") == pages(tmp_path / "b")
    folders = {p.parent.name for p in src.glob("*/__init__.py")}
    assert {f"Code-{f}.md" for f in folders} | {"Code-top-level.md", "Code.md"} <= set(pages(tmp_path / "a"))


# Never on the public wiki: a private decision's number, a path on someone's machine, an email address.
DECISION = re.compile(r"\bD\d{1,3}\b")
LOCAL_PATH = re.compile(r"/home/|/Users/|[A-Za-z]:\\\\|~/")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def test_the_real_pages_name_no_decision_local_path_or_email(tmp_path):
    """PY-CODEREF-006: The generated pages of the real package hold no decision number, local path or email

    Given the code reference generated from the package's source
    When every page is searched
    Then no page names a decision number (D followed by digits)
    And no page holds a path on someone's machine
    And no page holds an email address
    """
    code_reference.generate(ROOT / "src" / "traceconomics", tmp_path, REPO, COMMIT, ROOT)
    found = []
    for name, data in pages(tmp_path).items():
        for i, line in enumerate(data.decode("utf-8").splitlines(), 1):
            for kind, pattern in (("decision", DECISION), ("local path", LOCAL_PATH), ("email", EMAIL)):
                for hit in pattern.findall(line):
                    found.append(f"{name}:{i}: {kind}: {hit}")
    assert not found, "\n".join(found)


def test_the_command_line_needs_a_commit_hash(tmp_path):
    """PY-CODEREF-007: The command line refuses a commit that isn't a hash, and writes the pages with one

    Given the generator run from the command line
    When it is run with a branch name as the commit, then with a commit hash
    Then the run with the branch name stops with an error and writes nothing
    And the run with the hash writes the pages and lists them
    """
    script = ROOT / "tests" / "catalog" / "code_reference.py"
    src = made_up(tmp_path)
    args = [sys.executable, "-I", str(script), "--src", str(src), "--out", str(tmp_path / "w"), "--repo", REPO]
    bad = subprocess.run([*args, "--commit", "main"], capture_output=True, text=True)
    assert bad.returncode != 0 and "commit hash" in bad.stderr
    assert not (tmp_path / "w").exists()
    good = subprocess.run([*args, "--commit", COMMIT], capture_output=True, text=True)
    assert good.returncode == 0 and "Code-engine" in good.stdout


MAP_COMMIT = "fedcba9876543210fedcba9876543210fedcba98"


def entry(lines=0, unit=0, integration=0, imported=0, none=0, no_test=(), tests=((), ()), **members):
    return {
        "lines": lines,
        "unit": unit,
        "integration": integration,
        "imported": imported,
        "none": none,
        "no_test": [list(r) for r in no_test],
        "tests": {"unit": list(tests[0]), "integration": list(tests[1])},
        **({"members": members} if members else {}),
    }


def store(tmp_path: Path) -> Path:
    """A stored code map and catalog for the made-up package, from an earlier commit than the pages'."""
    folder = tmp_path / "store"
    folder.mkdir()
    tests = ["tests/test_job.py::test_run", "tests/test_lock.py::test_take", "tests/test_orphan.py::test_x"]
    modules = {
        "src/traceconomics/__init__.py": entry(),
        "src/traceconomics/job.py": entry(
            6,
            2,
            1,
            2,
            1,
            [(12, 13)],
            ([0], [1, 2]),
            run=entry(2, unit=1, imported=1, tests=([0], [])),
            Lock=entry(3, integration=1, imported=2, tests=([], [1])),
            **{"Lock.take": entry(2, integration=1, imported=1, tests=([], [1]))},
        ),
        "src/traceconomics/engine/chain.py": entry(
            3,
            imported=1,
            none=2,
            no_test=[(9, 9), (13, 13)],
            link=entry(2, imported=1, none=1),
            spare=entry(1, none=1),
            Point=entry(2, imported=2),
        ),
    }
    code_map = {"schema": 1, "commit": MAP_COMMIT, "back-end": {"tests": tests, "modules": modules}}
    (folder / "code-map.json").write_text(json.dumps(code_map), encoding="utf-8")

    def case(cid, node, layer, title, file=None):
        return {
            "id": cid,
            "suite": "pytest",
            "node": node,
            "layer": layer,
            "title": title,
            "file": file or node.split("::")[0],
        }

    cases = [
        case("PY-JOB-001", "tests/test_job.py::test_run", "unit", "The job runs"),
        case("PY-LOCK-001", "tests/test_lock.py::test_take", "integration", "The lock is taken"),
        case("PY-DOCS-001", "tests/test_docs.py::test_docs", "repository", "Every part has a docstring"),
        case("PY-HELP-001", "tests/test_help.py::test_helper", "unit", "A helper under tests"),
        {"id": "PW-X-001", "suite": "playwright", "node": "a", "title": "Not pytest", "file": "a"},
    ]
    (folder / "catalog.json").write_text(json.dumps({"cases": cases}), encoding="utf-8")
    return folder


def test_the_pages_show_what_the_tests_run(tmp_path):
    """PY-CODEREF-008: With a stored code map, the pages show each module's and member's tests, joined to their cases

    Given the made-up package, and a stored code map from an earlier commit and a catalog with unit, integration and repository cases
    When the code reference is generated with that store
    Then each page names the map's commit and says it is earlier than the page's
    And each public member shows its tests per layer, or "imported only", or "no test", and a class of definitions alone shows none of them
    And each module shows its lines by status, the lines no test runs linked at the map's commit, and its cases by layer behind a summary
    And a case links to its steps on the pytest page, and a test without a case shows its node ID
    And a module newer than the map says it is not in the coverage run yet
    And the overview adds each package's lines, the share run by a test and the lines no test runs
    And it lists the repository checks by test file, the unit and integration tests that run no package code, and the test runs without a case
    """
    out = tmp_path / "wiki"
    code_reference.generate(made_up(tmp_path), out, REPO, COMMIT, store=store(tmp_path))
    top = (out / "Code-top-level.md").read_text(encoding="utf-8")
    assert f"coverage of commit [`fedcba9`](https://github.com/{REPO}/commit/{MAP_COMMIT})" in top
    assert "an earlier commit than this page's" in top
    assert "One run of the job. · tests: unit 1" in top
    assert "Take the lock. · tests: integration 1" in top
    assert (
        "**Tests:** 6 lines with code: run by unit tests 2, by integration tests only 1, imported only 2, no test 1 "
        f"(lines [12–13](https://github.com/{REPO}/blob/{MAP_COMMIT}/src/traceconomics/job.py#L12-L13))."
    ) in top
    assert "<details><summary>Test cases that run it: unit 1, integration 2</summary>" in top
    assert "Unit:\n\n- [PY-JOB-001](Tests-pytest#py-job-001) The job runs" in top
    assert (
        "- [PY-LOCK-001](Tests-pytest#py-lock-001) The lock is taken\n- `tests/test_orphan.py::test_x` (no case)" in top
    )
    engine = (out / "Code-engine.md").read_text(encoding="utf-8")
    assert "One month's link. · **imported only**" in engine and "Never called. · **no test**" in engine
    assert "): A point.\n" in engine  # definitions only: nothing a test could run
    assert "_Not in the coverage run yet: the module is newer than the code map._" in engine
    overview = (out / "Code.md").read_text(encoding="utf-8")
    assert "| Lines with code | Run by a test | Imported only | No test |" in overview
    assert "| 2 | 3 | 6 | 3 (50%) | 2 (33%) | 1 (17%) |" in overview  # the top-level modules' row
    assert "## Checks on the code itself" in overview
    assert "- `tests/test_docs.py`\n  - [PY-DOCS-001](Tests-pytest#py-docs-001) Every part has a docstring" in overview
    assert "- [PY-HELP-001](Tests-pytest#py-help-001) A helper under tests (unit)" in overview
    assert "## Test runs without a case\n\n- `tests/test_orphan.py::test_x`" in overview
    assert "PW-X-001" not in overview


def test_a_store_without_a_map_changes_nothing(tmp_path):
    """PY-CODEREF-009: A store without a code map gives the same pages as no store

    Given the made-up package, and a store holding a catalog but no code map yet
    When the code reference is generated with the store, and again without it
    Then both give the same pages, byte for byte
    """
    src = made_up(tmp_path)
    folder = store(tmp_path)
    (folder / "code-map.json").unlink()
    code_reference.generate(src, tmp_path / "a", REPO, COMMIT, store=folder)
    code_reference.generate(src, tmp_path / "b", REPO, COMMIT)
    assert pages(tmp_path / "a") == pages(tmp_path / "b")
