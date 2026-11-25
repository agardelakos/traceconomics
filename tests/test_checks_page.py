"""The wiki page Checks (tests/catalog/checks_page.py): the registry stays complete, the page is right.

Most tests run on a small made-up repository written here; three run on the real one, because what
they guard (the registry is complete, identical bytes, nothing private) is about the real files.
"""

import json
import re
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "catalog"))
import checks_page  # noqa: E402

pytestmark = pytest.mark.repository

ROOT = Path(__file__).resolve().parent.parent
REPO = "owner/name"
DECISION = re.compile(r"\bD\d{1,3}\b")
LOCAL_PATH = re.compile(r"/home/|/Users/|[A-Za-z]:\\\\|~/")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

REGISTRY = """
[[ci]]
key = "python"
name = "Python tests"
what = "The suite."
local = "pytest"
required = true

[[ci]]
key = "codeql"
name = "Code scanning"
what = "CodeQL."
required = "code scanning"

[[ci]]
key = "badges"
name = "Badges"
what = "Badges."
check = false

[[gate]]
name = "Python coverage"
what = "Fails below the floor."
where = "tests/coverage/overview.py"
floor = { file = "tests/coverage/overview.py", pattern = '^RATCHET = ([0-9.]+)' }

[[release]]
key = "store"
name = "Update the store"
what = "Files in."
check = false

[[release]]
key = "check-v1"
name = "HICP rebuilt"
what = "The engine rebuilds the HICP."
local = ["one", "two"]

[[after]]
name = "Watchdog"
what = "The heartbeat."
when = "daily"
where = ".github/workflows/watchdog.yml"
"""

FILES = {
    ".github/workflows/tests.yml": """
        name: pipeline
        on:
          push:
            branches: [main]
        jobs:
          python:
            runs-on: ubuntu-24.04
            steps:
              - run: pytest
          codeql:  # the code scan
            runs-on: ubuntu-24.04
          badges:
            needs: [python]
        """,
    ".github/workflows/watchdog.yml": "name: watchdog\n",
    "src/traceconomics/release.py": """
        def steps(cfg):
            return [
                Step("store", ("a",)),
                Step(
                    "check-v1",
                    ("b",),
                ),
            ]


        def promote(build_id):
            Step("promote", ("c",))
        """,
    "site/scripts/checks.mjs": """
        // Checks on the built site.
        //
        //  1. Text: both languages have the same keys.
        //  2. Sources: every source key exists in the
        //     bibliography.

        import x from "y";
        // 3. Not a header line.
        """,
    "pyproject.toml": """
        [tool.ruff]
        line-length = 120
        target-version = "py314"

        [tool.ruff.lint]
        select = ["E4", "F"]
        """,
    "site/.prettierrc.json": '{ "printWidth": 100 }\n',
    "site/eslint.config.mjs": """
        import js from "@eslint/js";
        import tseslint from "typescript-eslint";

        export default [js.configs.recommended, ...tseslint.configs.recommended];
        """,
    "tests/coverage/overview.py": "FLOOR = 90\nRATCHET = 87.5\n",
    "tests/test_files.py": '''
        """The saved files are untouched. More detail here.

        A second paragraph.
        """
        import pytest

        pytestmark = pytest.mark.repository
        ''',
    "tests/test_engine.py": '"""The engine."""\nimport pytest\n\npytestmark = pytest.mark.unit\n',
}


def made_up(tmp_path: Path, registry: str = REGISTRY, **changes: str) -> Path:
    """A small repository with every file the page is made from; `changes` replaces files by path."""
    root = tmp_path / "repo"
    files = {**FILES, **{k.replace("__", "/"): v for k, v in changes.items()}}
    for rel, text in {**files, "tests/catalog/checks.toml": registry}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8", newline="\n")
    return root


def rules(contexts: list[str], scanning: bool = True) -> list[dict]:
    """GitHub's JSON for a branch's rules, cut down to the two rules the page reads."""
    out = [
        {"type": "deletion"},
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": c, "integration_id": 1} for c in contexts]},
        },
    ]
    return out + (
        [{"type": "code_scanning", "parameters": {"code_scanning_tools": [{"tool": "CodeQL"}]}}] if scanning else []
    )


def test_the_real_registry_is_complete():
    """PY-CHECKS-001: The real registry has exactly one entry for every CI job and release step

    Given the repository's own registry, workflow, release steps and site checks
    When the page generator compares them
    Then it finds no job or step without an entry, no entry without its job or step
    And the site checks are numbered 1 to N without a gap
    """
    assert checks_page.problems(ROOT) == []


def test_a_job_or_step_without_an_entry_is_found(tmp_path):
    """PY-CHECKS-002: A new CI job or release step without an entry, or an entry without one, is reported

    Given a made-up repository whose registry matches its sources
    When a job and a release step are added to the sources but not to the registry
    And an entry names a job that no longer exists
    Then each of the three is reported, by name
    And a promote step outside the build's steps is not taken for one of them
    """
    root = made_up(tmp_path)
    assert checks_page.problems(root) == []
    workflow = FILES[".github/workflows/tests.yml"].rstrip(" ") + "          same-in-both:\n            runs-on: x\n"
    release = FILES["src/traceconomics/release.py"].replace(
        'Step("store", ("a",)),', 'Step("store", ("a",)),\n                Step("export", ("e",)),'
    )
    registry = REGISTRY.replace('key = "badges"', 'key = "badge"')
    root = made_up(
        tmp_path / "2",
        registry,
        **{".github/workflows/tests.yml": workflow, "src/traceconomics/release.py": release},
    )
    found = checks_page.problems(root)
    assert any("job 'same-in-both'" in p and "has no entry" in p for p in found)
    assert any("job 'badges'" in p and "has no entry" in p for p in found)
    assert any("job 'badge'" in p and "is not in" in p for p in found)
    assert any("step 'export'" in p and "has no entry" in p for p in found)
    assert not any("promote" in p for p in found)


def test_the_jobs_are_read_only_under_jobs():
    """PY-CHECKS-003: Only the keys directly under `jobs:` are read as jobs

    Given a workflow with keys under `on:`, jobs with a comment after their name, and nested keys
    When its jobs are read
    Then the result is the job names in order, and nothing from `on:` or inside a job
    """
    text = textwrap.dedent(FILES[".github/workflows/tests.yml"])
    assert checks_page.ci_jobs(text) == ["python", "codeql", "badges"]


def test_a_gap_in_the_site_checks_numbers_is_found(tmp_path):
    """PY-CHECKS-004: The site checks are read from the header only, and a gap in their numbers is reported

    Given a made-up checks.mjs with two numbered header checks, one over two lines, and a numbered comment below
    When its checks are read
    And a copy with check 2 renumbered 3 is checked
    Then they are the two header checks, each on one line, and the comment below is ignored
    And the copy's gap is reported
    """
    root = made_up(tmp_path)
    text = (root / "site/scripts/checks.mjs").read_text(encoding="utf-8")
    assert checks_page.site_checks(text) == [
        (1, "Text: both languages have the same keys."),
        (2, "Sources: every source key exists in the bibliography."),
    ]
    gap = FILES["site/scripts/checks.mjs"].replace("//  2. Sources", "//  3. Sources")
    root = made_up(tmp_path / "2", **{"site/scripts/checks.mjs": gap})
    assert any("numbered [1, 3]" in p for p in checks_page.problems(root))


def test_the_repository_checks_are_the_files_marked_repository(tmp_path):
    """PY-CHECKS-005: The repository checks are the test files marked `repository`, with their docstring's first sentence

    Given a made-up repository with one test file marked repository and one marked unit
    When its repository checks are read
    Then only the first is listed, with the first sentence of its docstring
    """
    root = made_up(tmp_path)
    assert checks_page.repository_tests(root) == [("tests/test_files.py", "The saved files are untouched.")]


def test_the_required_checks_are_compared_with_the_branch_rules():
    """PY-CHECKS-006: The registry's required checks must match the branch rules on main

    Given the made-up registry, which requires `python` and code scanning results
    When it is compared with rules that require the same
    And with rules that require another check too
    And with rules that require no code scanning
    Then nothing is reported for the first
    And each difference is reported for the other two
    """
    reg = checks_page.tomllib.loads(REGISTRY)
    assert checks_page.required_problems(reg, rules(["python"])) == []
    more = checks_page.required_problems(reg, rules(["python", "lint"]))
    assert len(more) == 1 and "['lint', 'python']" in more[0]
    no_scan = checks_page.required_problems(reg, rules(["python"], scanning=False))
    assert len(no_scan) == 1 and "code scanning" in no_scan[0]


def test_nothing_is_written_while_anything_disagrees(tmp_path):
    """PY-CHECKS-007: The page is not written while the registry disagrees with the sources or the rules

    Given a made-up repository with a job missing from its registry
    And a complete made-up repository
    When the page is generated for the first
    And for the second, with rules that require another check
    Then both stop, the first naming the job
    And no page is written
    """
    workflow = FILES[".github/workflows/tests.yml"].rstrip(" ") + "          extra:\n            runs-on: x\n"
    root = made_up(tmp_path, **{".github/workflows/tests.yml": workflow})
    out = tmp_path / "wiki"
    with pytest.raises(SystemExit, match="job 'extra'"):
        checks_page.generate(out, REPO, root=root)
    assert not (out / "Checks.md").exists()
    root = made_up(tmp_path / "2")
    with pytest.raises(SystemExit, match="rules on main require"):
        checks_page.generate(out, REPO, rules(["python", "site"]), root=root)
    assert not (out / "Checks.md").exists()


def test_the_page_shows_each_part(tmp_path):
    """PY-CHECKS-008: The page shows every job, step, site check, repository check, gate and setting

    Given a made-up repository and rules that match its registry
    When the page is generated
    Then it lists the jobs with whether each is required, and names the badges job as not a check
    And it lists the linters' settings read from their files, the site checks and the repository check
    And it shows the coverage floor read from the code
    And the release steps in order, as check or build, with their commands in order
    And the checks after a build
    And it says the required checks were checked against the branch rules
    """
    root = made_up(tmp_path)
    checks_page.generate(tmp_path / "wiki", REPO, rules(["python"]), root=root)
    page = (tmp_path / "wiki" / "Checks.md").read_text(encoding="utf-8")
    assert page.startswith("> Generated, do not edit.")
    assert "| `python`: Python tests | yes | The suite. | `pytest` |" in page
    assert "| `codeql`: Code scanning | code scanning results |" in page
    assert "Not a check: `badges` (Badges.)" in page
    assert "width 120; linter, rule sets `E4`, `F`; target `py314`" in page
    assert "`@eslint/js` recommended, `typescript-eslint` recommended" in page
    assert "Stylelint" not in page
    assert (
        "1. Text: both languages have the same keys.\n2. Sources: every source key exists in the bibliography." in page
    )
    assert (
        "| [`tests/test_files.py`](https://github.com/owner/name/blob/main/tests/test_files.py) | The saved files are untouched. |"
        in page
    )
    assert "test_engine.py" not in page
    assert "Floor: 87.5%." in page
    assert "| 1 | `store`: Update the store | build |" in page
    assert "| 2 | `check-v1`: HICP rebuilt | check | The engine rebuilds the HICP. | `one`, then `two` |" in page
    assert "| Watchdog | daily | The heartbeat. |" in page
    assert "checked against the branch rules on `main`" in page


def test_stylelint_is_listed_once_it_is_set_up(tmp_path):
    """PY-CHECKS-009: Stylelint appears on the page once its configuration exists

    Given a made-up repository with a Stylelint configuration that extends two shared configs
    When the page is generated
    Then the code style table lists Stylelint with the two configs
    """
    config = 'export default {\n  extends: ["stylelint-config-standard", "./tokens.mjs"],\n};\n'
    root = made_up(tmp_path, **{"site/stylelint.config.mjs": config})
    checks_page.generate(tmp_path / "wiki", REPO, root=root)
    page = (tmp_path / "wiki" / "Checks.md").read_text(encoding="utf-8")
    assert "| Stylelint (the site's CSS) | extends `stylelint-config-standard`, `./tokens.mjs` |" in page


def test_the_real_page_gives_the_same_bytes_and_nothing_private(tmp_path):
    """PY-CHECKS-010: The real page is byte-identical from run to run and holds nothing private

    Given the repository's own files
    When the page is generated twice into two folders
    Then the two pages are byte-identical
    And the page holds no decision number, no path on someone's machine and no email address
    """
    checks_page.generate(tmp_path / "a", REPO, root=ROOT)
    checks_page.generate(tmp_path / "b", REPO, root=ROOT)
    a = (tmp_path / "a" / "Checks.md").read_bytes()
    assert a == (tmp_path / "b" / "Checks.md").read_bytes()
    found = []
    for i, line in enumerate(a.decode("utf-8").splitlines(), 1):
        for kind, pattern in (("decision", DECISION), ("local path", LOCAL_PATH), ("email", EMAIL)):
            found += [f"{i}: {kind}: {hit}" for hit in pattern.findall(line)]
    assert not found, "\n".join(found)


def test_the_command_line_reads_the_rules(tmp_path):
    """PY-CHECKS-011: The command line reads the rules from a file and writes the page

    Given a made-up repository and a file with rules that match its registry
    When the generator's command line is run with --rules
    Then it writes the page and names it
    """
    root = made_up(tmp_path)
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(rules(["python"])), encoding="utf-8")
    real = checks_page.ROOT
    try:
        checks_page.ROOT = root
        checks_page.main(["--out", str(tmp_path / "wiki"), "--repo", REPO, "--rules", str(path)])
    finally:
        checks_page.ROOT = real
    assert (tmp_path / "wiki" / "Checks.md").is_file()


def test_text_from_sources_stays_text(tmp_path):
    """PY-CHECKS-012: Tags named in a source stay text, and Stylelint's opening comment describes it

    Given a made-up repository whose site check and repository test name an HTML tag
    Given a Stylelint configuration that opens with a comment of two paragraphs
    When the page is generated
    Then each tag outside a code span is escaped and each one inside a code span is left as typed
    Then the code style table gives the comment's first sentence after the shared configs
    """
    header = (
        "// Checks.\n//\n//  1. Text: no <style> blocks, no `<nav>` in pages.\n//  2. Sources: none.\n\nimport x;\n"
    )
    test = '"""No <script> in the files.\n\nMore."""\n\nimport pytest\n\npytestmark = pytest.mark.repository\n'
    config = (
        "// Stylelint: the recommended rules, then the site's own. Second sentence.\n"
        "// Still the first paragraph.\n//\n// Another paragraph.\n"
        'export default {\n  extends: ["stylelint-config-recommended"],\n};\n'
    )
    root = made_up(
        tmp_path,
        **{"site/scripts/checks.mjs": header, "tests/test_files.py": test, "site/stylelint.config.mjs": config},
    )
    checks_page.generate(tmp_path / "wiki", REPO, root=root)
    page = (tmp_path / "wiki" / "Checks.md").read_text(encoding="utf-8")
    assert "1. Text: no &lt;style> blocks, no `<nav>` in pages." in page
    assert "| No &lt;script> in the files. |" in page
    assert (
        "| Stylelint (the site's CSS) | extends `stylelint-config-recommended`. "
        "The recommended rules, then the site's own. |"
    ) in page
