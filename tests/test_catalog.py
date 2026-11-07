"""The test catalog's own tooling (tests/catalog/): reading cases, the validator, the run history
and the wiki pages. Synthetic inputs only: small result files written here, never a real run."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent / "catalog"))
import cases as cases_mod  # noqa: E402
import collect  # noqa: E402
import history  # noqa: E402
import validate  # noqa: E402
import vm_pull  # noqa: E402
import wiki  # noqa: E402

GOOD = """PY-ENG-012: chain-linking carries December over

Given an index with a December link month
And a second year of months
When the next year is chain-linked
Then the December value carries over unchanged

The reason for the rule, kept as notes.
"""


def case(**kw):
    base = dict(id="PY-ENG-001", suite="pytest", title="t", file="tests/test_x.py", line=1,
                node="tests/test_x.py::test_a", given=["g"], when=["w"], then=["t"])
    base.update(kw)
    return cases_mod.Case(**base)


def cat(*cs, missing=()):
    return {"schema": 1, "commit": "abc1234", "missing": list(missing), "cases": [c.to_json() for c in cs]}


# Reading the cases ------------------------------------------------------------------------------

def test_docstring_steps_and_notes():
    """PY-CAT-001: a docstring's case is read into its ID, title, steps and notes

    Given a docstring with an ID and title, Given/And/When/Then steps and a closing note
    When its case is read
    Then the ID and the title are read from the first line
    And the Given steps include the And line that follows them
    And the When and Then steps are read
    And the text after the steps is kept as notes
    And no problem is reported
    """
    d = cases_mod.from_docstring(GOOD)
    assert d["id"] == "PY-ENG-012" and d["title"] == "chain-linking carries December over"
    assert d["given"] == ["an index with a December link month", "a second year of months"]
    assert d["when"] == ["the next year is chain-linked"]
    assert d["then"] == ["the December value carries over unchanged"]
    assert d["notes"] == "The reason for the rule, kept as notes."
    assert d["problems"] == []


@pytest.mark.parametrize("doc, problem", [
    (None, "no docstring"),
    ("A plain sentence.", "first line is not 'ID: title'"),
    ("PY-ENG-001: t\n\nWhen w\nGiven g\nThen t", "Given after When: steps go Given, When, Then"),
    ("PY-ENG-001: t\n\nAnd g\nWhen w\nThen t", "And before any Given/When/Then"),
    ("PY-ENG-001: t\n\nGiven g\nsomething else\nThen t", "not a Given/When/Then line: 'something else'"),
    ("PY-ENG-001: t\n\nGiven g\nWhen w\nThen t\nAnd when x\nThen y", "'And when …' hides a step: list every action under When"),
], ids=["none", "no-header", "order", "and-first", "stray-line", "and-when"])
def test_docstring_problems(doc, problem):
    """PY-CAT-002: a docstring that breaks the convention is reported

    Given a docstring that is missing, has no "ID: title" first line, puts Given after When, starts with And, or has a line that is not a step
    When its case is read
    Then the matching problem is reported
    """
    assert problem in cases_mod.from_docstring(doc)["problems"]


def test_annotations_and_meta():
    """PY-CAT-003: a case is read from Playwright annotations and from Vitest meta

    Given Playwright annotations with an ID, Given/And/When/Then steps and a fixme that names an issue
    And Vitest meta with an ID and steps written as a string or a list
    When a case is read from each
    Then from the annotations the ID is read, the And line joins the Given steps and the issue number is a defect
    And from the meta the ID is read and each step becomes a list
    """
    a = cases_mod.from_annotations([
        {"type": "id", "description": "PW-CALC-001"}, {"type": "given", "description": "a preset"},
        {"type": "and", "description": "English"}, {"type": "when", "description": "untouched"},
        {"type": "then", "description": "the published rate"},
        {"type": "fixme", "description": "broken in Safari, #42"}])
    assert a["id"] == "PW-CALC-001" and a["given"] == ["a preset", "English"] and a["defects"] == [42]
    m = cases_mod.from_meta({"id": "VT-FMT-001", "given": "an amount", "when": ["formatted"], "then": "€ first"})
    assert (m["id"], m["given"], m["when"], m["then"]) == ("VT-FMT-001", ["an amount"], ["formatted"], ["€ first"])


def test_issue_links():
    """PY-CAT-004: issue numbers are read from a reason

    Given a reason naming issues #12 and #7, and two hashes inside other words
    When the issue numbers are read
    Then they are 7 and 12, sorted, and the hashes inside words are not issues
    """
    assert cases_mod.issues("xfail: rounding, see #12 and #7; not a/#9 or x#3") == [7, 12]


# Collecting -------------------------------------------------------------------------------------

def test_pytest_plugin_collects_outlines(tmp_path):
    """PY-CAT-005: a real pytest collection reads an outline and a test with no case

    Given a throwaway test file with a parametrized test that has a case and an xfail test that names an issue but has no case
    When it is collected through pytest
    Then the parametrized test is one case with its ID and both examples
    And the other test has no ID and the xfail's issue as a defect

    The plugin through a real pytest collection, on a throwaway test file.
    """
    f = tmp_path / "test_demo.py"
    f.write_text(textwrap.dedent('''
        import pytest

        @pytest.mark.parametrize("n", [1, 2], ids=["one", "two"])
        def test_outline(n):
            """PY-DEMO-001: an outline

            Given a number
            When it is checked
            Then it is positive
            """

        @pytest.mark.xfail(reason="known, #5")
        def test_plain():
            "No case yet."
    '''), encoding="utf-8")
    items = collect.pytest_items([str(f), "--rootdir", str(tmp_path), "-c", "/dev/null"])
    got = {c.node.split("::")[-1]: c for c in collect.from_pytest(items, "pytest")}
    assert got["test_outline"].id == "PY-DEMO-001" and got["test_outline"].examples == ["one", "two"]
    assert got["test_plain"].id is None and got["test_plain"].defects == [5]


def test_playwright_listing_and_loops():
    """PY-CAT-006: tests generated by a loop in a Playwright listing become one outline

    Given a Playwright listing with the same case in English and Greek, tagged @smoke
    When the cases are read and outlines merged
    Then there is one case
    And its file is the path from the repository root and its examples are both test titles
    And its title is the first example, as the titles share too little to name it
    And titles that share a long enough tail are named by that tail
    And its tag is smoke, with no problem
    """
    listing = {"config": {"rootDir": str(collect.ROOT / "site/tests/ui")}, "suites": [{
        "title": "calc.ui.ts", "file": "calc.ui.ts", "specs": [
            {"title": f"{lang}: untouched", "file": "calc.ui.ts", "line": 3, "tags": ["@smoke"],
             "tests": [{"annotations": [{"type": "id", "description": "PW-CALC-001"},
                                        {"type": "given", "description": "g"}, {"type": "when", "description": "w"},
                                        {"type": "then", "description": "t"}]}]}
            for lang in ("en", "el")]}]}
    merged = collect.merge_outlines(collect.from_playwright(listing))
    assert len(merged) == 1
    c = merged[0]
    assert c.file == "site/tests/ui/calc.ui.ts" and c.examples == ["en: untouched", "el: untouched"]
    assert c.title == "en: untouched"                                  # too little in common to name it
    assert collect.shared_title(["en: untouched, it shows the rate", "el: untouched, it shows the rate"]) \
        == "untouched, it shows the rate"
    assert c.tags == ["smoke"] and c.problems == []


def test_an_outline_over_pages_takes_the_title_given_with_its_case():
    """PY-CAT-026: an outline over pages takes the title given with its case

    Given Playwright tests made one per page, whose own titles are the pages' addresses
    And their case gives a title
    When they are listed and merged
    Then the one case carries the given title
    And its examples are the addresses
    """
    ann = [{"type": "id", "description": "PW-A11Y-001"}, {"type": "title", "description": "every page passes"},
           {"type": "given", "description": "g"}, {"type": "when", "description": "w"}, {"type": "then", "description": "t"}]
    listing = {"config": {"rootDir": str(collect.ROOT / "site/tests/ui")}, "suites": [{
        "title": "a11y.ui.ts", "file": "a11y.ui.ts",
        "specs": [{"title": page, "file": "a11y.ui.ts", "line": 3, "tests": [{"annotations": ann}]} for page in ("/el/", "/en/")]}]}
    (c,) = collect.merge_outlines(collect.from_playwright(listing))
    assert c.title == "every page passes" and c.named and c.examples == ["/el/", "/en/"]


def test_a_copied_id_is_a_duplicate_not_an_outline():
    # Two pytest functions under one ID: never an outline (parametrize is), always a duplicate.
    """PY-CAT-007: a copied ID is a duplicate, not an outline

    Given two pytest functions under one ID
    And two Playwright tests under one ID with different steps
    And two Playwright tests under one ID with the same steps
    When outlines are merged and the catalog is validated
    Then the two pytest functions give a duplicate-id error
    And the Playwright tests with different steps give a duplicate-id error
    And the Playwright tests with the same steps merge into one case
    """
    a, b = case(title="a"), case(title="b", node="tests/test_x.py::test_b")
    assert ("duplicate-id", True) in rules(cat(*collect.merge_outlines([a, b])))
    # Playwright tests under one ID with different steps: a copied test, not a loop.
    pw = dict(suite="playwright", id="PW-CALC-001", file="site/tests/ui/c.ui.ts")
    x, y = case(title="x", **pw), case(title="y", then=["other"], **pw)
    assert ("duplicate-id", True) in rules(cat(*collect.merge_outlines([x, y])))
    assert len(collect.merge_outlines([case(title="en: a", **pw), case(title="el: a", **pw)])) == 1


# The validator ----------------------------------------------------------------------------------

def rules(catalog, strict=None, mapping=None, obsolete=(), require_all=False):
    obsolete = obsolete if isinstance(obsolete, dict) else set(obsolete)
    return {(f.rule, f.error) for f in validate.check(catalog, strict or {}, mapping or {}, obsolete, require_all)}


def test_ratchet_warns_outside_strict_files():
    """PY-CAT-008: a missing ID warns, and is an error only in strict files

    Given a test with no case ID
    When the catalog is validated
    Then missing-id is a warning
    And it is an error when its file is listed as strict
    And it is an error when every file is strict
    """
    c = case(id=None, title="")
    assert rules(cat(c)) == {("missing-id", False)}
    assert rules(cat(c), strict={"files": ["tests/test_x.py"]}) == {("missing-id", True)}
    assert rules(cat(c), strict={"all": True}) == {("missing-id", True)}


def test_always_errors():
    """PY-CAT-009: the rules that are always errors

    Given a catalog with no file marked strict
    When it is validated
    Then an ID with another suite's prefix is a bad-id error
    And an ID not in the PREFIX-AREA-NNN form is a bad-id error
    And one ID on tests in two files is a duplicate-id error
    And an ID that belonged to a removed test with another title or file is a reused-id error
    And an ID back on the same test it was removed from (a revert) gives no finding
    And a suite that was not collected, when every suite is required, is an incomplete error
    """
    assert ("bad-id", True) in rules(cat(case(id="PW-ENG-001")))          # another suite's prefix
    assert ("bad-id", True) in rules(cat(case(id="PY-eng-1")))
    dup = rules(cat(case(), case(file="tests/test_y.py", node="tests/test_y.py::test_a")))
    assert ("duplicate-id", True) in dup
    gone = {"PY-ENG-001": {"suite": "pytest", "file": "tests/test_old.py", "title": "another test"}}
    assert ("reused-id", True) in rules(cat(case()), obsolete=gone)
    back = {"PY-ENG-001": {"suite": "pytest", "file": "tests/test_x.py", "title": "t"}}
    assert rules(cat(case()), obsolete=back) == set()                 # a revert keeps its ID
    assert ("incomplete", True) in rules(cat(case(), missing=["selenium"]), require_all=True)


def test_missing_steps():
    """PY-CAT-010: a case without a Then step is reported in a strict file

    Given a case with no Then step, in a catalog where every file is strict
    When the catalog is validated
    Then the only finding is a missing-steps error
    """
    assert rules(cat(case(then=[])), strict={"all": True}) == {("missing-steps", True)}


def test_mapping():
    """PY-CAT-011: the cross-suite mapping of browser cases is checked

    Given a Playwright case and a Selenium case
    When they are mapped to one shared case
    And they are not mapped, first as the backfill allows, then with the mapping required to be complete
    And the mapping lists a case under the wrong suite or names an unknown case
    And each is mapped to a shared case of its own, one with a reason and one without
    Then mapped together, there is no finding
    And unmapped, they are a warning, and an error once the mapping must be complete
    And a wrong suite or an unknown case is a mapping error
    And of the two single-suite entries only the one without a reason is reported, asking why it is in one suite only
    """
    pw = case(id="PW-CALC-001", suite="playwright", file="site/tests/ui/c.ui.ts")
    sel = case(id="SEL-CALC-001", suite="selenium", file="tests/selenium/test_c.py")
    ok = {"TC-CALC-001": {"title": "t", "playwright": ["PW-CALC-001"], "selenium": ["SEL-CALC-001"]}}
    assert rules(cat(pw, sel), mapping=ok) == set()
    assert ("unmapped", False) in rules(cat(pw, sel))
    assert ("unmapped", True) in rules(cat(pw, sel), strict={"mapping_complete": True})
    wrong = {"TC-CALC-001": {"title": "t", "playwright": ["SEL-CALC-001"], "selenium": ["SEL-CALC-009"]}}
    assert ("mapping", True) in rules(cat(pw, sel), mapping=wrong)
    single = {"TC-CALC-001": {"title": "t", "playwright": ["PW-CALC-001"]},
              "TC-CALC-002": {"title": "t", "selenium": ["SEL-CALC-001"], "why": "Selenium only"}}
    found = validate.check(cat(pw, sel), {}, single, set(), False)
    assert [f.message for f in found if f.rule == "mapping"] == ["TC-CALC-001 is in one suite only: say why (`why = \"…\"`)"]


# The run history --------------------------------------------------------------------------------

JUNIT = """<?xml version="1.0"?><testsuites><testsuite>
<testcase classname="tests.test_x" name="test_a[one]" time="0.5"/>
<testcase classname="tests.test_x" name="test_a[two]" time="0.5"><failure message="boom"/></testcase>
<testcase classname="tests.test_x" name="test_b" time="0.1"><skipped/></testcase>
<testcase classname="tests.test_x" name="test_c" time="0.1"/>
<testcase classname="tests.test_local_x" name="" time="0"><skipped message="could not import 'pandas'"/></testcase>
</testsuite></testsuites>"""

PLAYWRIGHT = {"suites": [{"specs": [{"title": "en: untouched", "tests": [
    {"projectName": "chromium", "status": "flaky", "annotations": [{"type": "id", "description": "PW-CALC-001"}],
     "results": [{"duration": 100}, {"duration": 200}]}]}]}]}

VITEST = {"testResults": [{"name": "/x/format.test.ts", "assertionResults": [
    {"title": "euros", "status": "passed", "duration": 2, "meta": {"id": "VT-FMT-001"}},
    {"title": "other", "status": "passed", "duration": 1}]}]}


def make_record(tmp_path, commit="abc1234", started="2026-11-07T12:00:00Z", trigger="push"):
    (tmp_path / "junit.xml").write_text(JUNIT, encoding="utf-8")
    (tmp_path / "pw.json").write_text(json.dumps(PLAYWRIGHT), encoding="utf-8")
    (tmp_path / "vt.json").write_text(json.dumps(VITEST), encoding="utf-8")
    catalog = cat(case(), case(id="PY-ENG-002", node="tests/test_x.py::test_b"))
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    a = SimpleNamespace(catalog=tmp_path / "catalog.json", junit=[f"pytest={tmp_path / 'junit.xml'}"],
                        playwright=tmp_path / "pw.json", vitest=tmp_path / "vt.json", env=["platform=linux-x86_64"],
                        run_id="7", trigger=trigger, commit=commit, build=None, started=started, run_url=None)
    return history.record(a), catalog


def test_record_gives_each_result_to_its_case(tmp_path):
    """PY-CAT-012: a run record gives each test result to its case

    Given a catalog of two pytest cases, and JUnit, Playwright and Vitest result files
    When the run record is made
    Then a case with one failed example has the result failed, with each example's result
    And a skipped test's case is skipped
    And a Playwright test passed on retry is flaky, with its total duration and one retry
    And the Vitest case passed
    And the results with no case are counted per suite
    And the pytest suite's totals count passed, failed, flaky and skipped tests and the duration
    And the record passes the record check
    """
    rec, _ = make_record(tmp_path)
    assert rec["cases"]["PY-ENG-001"]["result"] == "failed"            # one example failed
    assert rec["cases"]["PY-ENG-001"]["examples"] == {"one": "passed", "two": "failed"}
    assert rec["cases"]["PY-ENG-002"]["result"] == "skipped"
    assert rec["cases"]["PW-CALC-001"] == {"suite": "playwright", "result": "flaky", "duration": 0.3, "retries": 1}
    assert rec["cases"]["VT-FMT-001"]["result"] == "passed"
    assert rec["no_case"] == {"pytest": 1, "vitest": 1}
    assert rec["suites"]["pytest"] == {"passed": 2, "failed": 1, "flaky": 0, "skipped": 1, "duration": 1.2}
    assert history.check_record(rec) == []


def test_the_microdata_job_counts_as_its_own_suite_but_feeds_pytest_cases(tmp_path):
    """PY-CAT-013: the microdata job counts as its own suite but feeds pytest cases

    Given JUnit results from the CI job that runs the tests with the microdata extra
    When they are read as the pytest-local suite
    Then the run has that suite only
    And the pytest case's result belongs to that suite
    """
    (tmp_path / "local.xml").write_text(JUNIT, encoding="utf-8")
    run = history.Run()
    history.read_junit(run, tmp_path / "local.xml", "pytest-local", cat(case()))
    run.finish()
    assert set(run.suites) == {"pytest-local"} and run.cases["PY-ENG-001"]["suite"] == "pytest-local"


def test_append_keeps_the_newest_and_never_forgets_an_obsolete_id(tmp_path):
    """PY-CAT-014: the history keeps the newest runs and never forgets an obsolete ID

    Given a run history that keeps three runs per trigger
    When four runs are appended
    And a test's case is removed in a later commit and the catalog is updated twice
    Then three run files are left
    And the obsolete IDs record the removed case's last commit and the commit that removed it
    """
    store = tmp_path / "store"
    for i in range(4):
        rec, catalog = make_record(tmp_path, started=f"2026-11-0{i + 1}T12:00:00Z")
        history.append(store, rec, catalog, keep=3)
    assert len(list((store / "runs/push").glob("*.json"))) == 3
    smaller = cat(case())                                              # PY-ENG-002's test removed
    smaller["commit"] = "def5678"
    history.update_catalog(store, smaller)
    history.update_catalog(store, cat(case()))
    obsolete = json.loads((store / "obsolete.json").read_text(encoding="utf-8"))
    assert obsolete["PY-ENG-002"]["last_commit"] == "abc1234" and obsolete["PY-ENG-002"]["removed_in"] == "def5678"


def test_the_worse_result_of_an_example_stands():
    """PY-CAT-015: the worse result of an example stands

    Given the same example run in both pytest jobs, failed in one and passed in the other
    When the run is finished
    Then the case's result is failed
    """
    run = history.Run()
    run.add("pytest", "PY-ENG-001", "test_a", "failed", 0.1)
    run.add("pytest-local", "PY-ENG-001", "test_a", "passed", 0.1)      # the same file in the other job
    run.finish()
    assert run.cases["PY-ENG-001"]["result"] == "failed"


def test_describe_titles_keep_examples_apart():
    """PY-CAT-016: Playwright describe titles keep examples apart

    Given one case with the same test title in two describe blocks, failing in one and passing in the other
    When the Playwright results are read
    Then each example is named by its block and title and keeps its own result
    """
    data = {"suites": [{"title": "c.ui.ts", "file": "c.ui.ts", "suites": [
        {"title": block, "file": "c.ui.ts", "specs": [{"title": "same title", "tests": [
            {"status": status, "annotations": [{"type": "id", "description": "PW-CALC-001"}], "results": [{}]}]}]}
        for block, status in (("on a phone", "unexpected"), ("on a desktop", "expected"))]}]}
    run = history.Run()
    history.read_playwright(run, data)
    run.finish()
    assert run.cases["PW-CALC-001"]["examples"] == {"on a phone › same title": "failed", "on a desktop › same title": "passed"}


def test_the_catalog_never_loses_ids_to_an_incomplete_run_and_a_revert_is_welcome(tmp_path):
    """PY-CAT-017: the catalog never loses IDs to an incomplete run, and a revert is welcome

    Given a stored catalog with a pytest and a Playwright case
    When a catalog where Playwright was not collected is stored
    And then one where the Playwright case's test is really removed
    And then one where the test comes back
    Then after the incomplete catalog no ID is obsolete and both cases are kept
    And after the removal its ID is obsolete
    And after it comes back no ID is obsolete
    """
    store = tmp_path / "store"
    store.mkdir()
    pw = case(id="PW-CALC-001", suite="playwright", file="site/tests/ui/c.ui.ts")
    history.update_catalog(store, cat(case(), pw))
    history.update_catalog(store, cat(case(), missing=["playwright"]))  # Playwright not collected
    obsolete = json.loads((store / "obsolete.json").read_text(encoding="utf-8"))
    stored = json.loads((store / "catalog.json").read_text(encoding="utf-8"))
    assert obsolete == {} and {c["id"] for c in stored["cases"]} == {"PY-ENG-001", "PW-CALC-001"}
    history.update_catalog(store, cat(case()))                         # its test really removed
    assert "PW-CALC-001" in json.loads((store / "obsolete.json").read_text(encoding="utf-8"))
    history.update_catalog(store, cat(case(), pw))                     # reverted
    assert json.loads((store / "obsolete.json").read_text(encoding="utf-8")) == {}


def test_a_bad_record_is_refused(tmp_path):
    """PY-CAT-018: a run record with an unknown trigger is refused

    Given a run record whose trigger is not a known one
    When it is appended to the history
    Then a ValueError says the trigger is unknown
    And the history store is not created
    """
    rec, _ = make_record(tmp_path)
    rec["trigger"] = "nightly"
    with pytest.raises(ValueError, match="unknown trigger"):
        history.append(tmp_path / "store", rec, None, 200)
    assert not (tmp_path / "store").exists()


# The wiki pages ---------------------------------------------------------------------------------

def test_flakiness():
    """PY-CAT-019: a case's flakiness is its share of result changes

    Given a case's recent results
    When its flakiness is computed
    Then fewer than five runs give no rate
    And steady passes give zero
    And one failure among passes gives 0.5 (two changes in four steps)
    And skipped runs are left out
    And a flaky run counts one change, not two, since flaky back to passed is not a change
    """
    assert wiki.flakiness(["passed"] * 4) is None                      # too few
    assert wiki.flakiness(["passed"] * 6) == 0
    assert wiki.flakiness(["passed", "failed", "passed", "passed", "passed"]) == 0.5
    assert wiki.flakiness(["passed", "skipped", "passed", "passed", "passed", "passed"]) == 0
    assert wiki.flakiness(["passed", "passed", "flaky", "passed", "passed", "passed"]) == 0.2   # one change


def test_pages(tmp_path):
    """PY-CAT-020: the generated wiki pages replace the old ones and leave hand-written pages alone

    Given a run history with one run, and a wiki with a stale generated page, a sidebar with a generated block and a hand-written home page
    When the wiki pages are generated
    Then a Tests page is written and the stale generated page is deleted
    And the hand-written page is untouched
    And the sidebar keeps its hand-written part, its generated block is replaced and it links to Tests-Runs
    And the pytest page starts with its title and a "Generated, do not edit." note
    And it lists each case with its title, last result and "too few runs" for flakiness
    And it links the case to its file and line at the catalog's commit
    """
    store, out = tmp_path / "store", tmp_path / "wiki"
    rec, catalog = make_record(tmp_path)
    history.append(store, rec, catalog, 200)
    out.mkdir()
    (out / "Tests-Old.md").write_text("stale", encoding="utf-8")
    (out / "_Sidebar.md").write_text("[Home](Home)\n\n<!-- generated:start -->\nold\n<!-- generated:end -->\n", encoding="utf-8")
    (out / "Home.md").write_text("hand-written", encoding="utf-8")
    pages = wiki.generate(store, out, "owner/repo", 10, 20)
    assert "Tests" in pages and not (out / "Tests-Old.md").exists()
    assert (out / "Home.md").read_text(encoding="utf-8") == "hand-written"
    sidebar = (out / "_Sidebar.md").read_text(encoding="utf-8")
    assert sidebar.startswith("[Home](Home)") and "old" not in sidebar and "[Runs](Tests-Runs)" in sidebar
    py = (out / "Tests-pytest.md").read_text(encoding="utf-8")
    assert py.startswith("# pytest cases\n\n> Generated, do not edit.")
    assert "| [PY-ENG-001](#py-eng-001) | t | ✗ | too few runs |" in py
    assert "https://github.com/owner/repo/blob/abc1234/tests/test_x.py#L1" in py


def test_scripts_run_from_the_command_line(tmp_path):
    """PY-CAT-021: the validator runs from the command line and fails on an error

    Given a catalog with a malformed ID
    When the validator runs as a script in isolated mode
    Then it exits with code 1
    And it prints the bad-id finding

    The validator as CI calls it: isolated mode, exit code 1 on an error.
    """
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(cat(case(id="PY-x"))), encoding="utf-8")
    done = subprocess.run([sys.executable, "-I", str(Path(__file__).parent / "catalog/validate.py"), str(p)],
                          capture_output=True, text=True)
    assert done.returncode == 1 and "[bad-id]" in done.stdout


# Release runs from the bucket ------------------------------------------------------------------

def bucket(files: dict[str, bytes]):
    """A fake read link: a listing (in pages of two) and downloads, as the bucket answers them."""
    names = sorted(files)

    def get(url, limit=10**9):
        base, _, query = url.partition("?")
        if query:
            q = dict(x.split("=", 1) for x in query.split("&"))
            start = q.get("start", "").replace("%2F", "/")
            rest = [n for n in names if n.startswith("results/") and n >= start]
            page = {"objects": [{"name": n, "size": len(files[n])} for n in rest[:2]]}
            if len(rest) > 2:
                page["nextStartWith"] = rest[2]
            return json.dumps(page).encode()
        return files[base.removeprefix("https://bucket/o/")]
    return get


def meta(**kw):
    m = {"schema": 1, "build": "20261107T120000Z", "commit": "abc1234", "step": "ui-test",
         "started": "2026-11-07T12:05:00Z", "environment": {"platform": "linux-aarch64", "data": "real"}, "result": "passed"}
    m.update(kw)
    return json.dumps(m).encode()


def test_release_runs_are_pulled_checked_and_stored_once(tmp_path):
    """PY-CAT-022: release test runs are pulled from the bucket, checked and stored once

    Given a bucket listed in pages of two, holding a ui-test run, a failed promote check, a smoke run with a bad commit, a smoke run still uploading and the link check's object
    When the release runs are pulled
    Then the ui-test and promote runs are written as run records
    And the only problem is the smoke run's missing commit; the run still uploading and the link check are skipped silently
    And the ui-test record carries its trigger, build, start time and environment
    And its Playwright case keeps its flaky result
    And the promote record counts one failed promote check
    And no downloaded results file is left behind
    And once those records are in the history, a second pull writes nothing
    """
    folder = "results/20261107T120000Z/ui-test-20261107T120500Z/"
    files = {
        folder + "meta.json": meta(),
        folder + "playwright.json": json.dumps(PLAYWRIGHT).encode(),
        "results/20261107T120000Z/promote-20261107T130000Z/meta.json": meta(step="promote", result="failed"),
        "results/20261107T120000Z/smoke-20261107T121000Z/meta.json": meta(step="smoke", commit="not a commit"),
        "results/20261107T120000Z/smoke-20261107T122000Z/playwright.json": b"{}",     # no meta yet: still uploading
        "results/check/20261107T111853Z.json": b"{}",                                  # the link check's object
    }
    store, out = tmp_path / "store", tmp_path / "out"
    written, problems = vm_pull.pull("https://bucket/o/", store, out, bucket(files))
    assert sorted(p.name for p in written) == ["20261107T120000Z-promote-20261107T130000Z.json",
                                               "20261107T120000Z-ui-test-20261107T120500Z.json"]
    assert problems == ["results/20261107T120000Z/smoke-20261107T121000Z/: ValueError: no commit"]
    ui = json.loads((out / "20261107T120000Z-ui-test-20261107T120500Z.json").read_text(encoding="utf-8"))
    assert ui["trigger"] == "ui-test" and ui["build"] == "20261107T120000Z" and ui["started"] == "2026-11-07T12:05:00Z"
    assert ui["environment"] == {"data": "real", "platform": "linux-aarch64"}
    assert ui["cases"]["PW-CALC-001"]["result"] == "flaky"
    promote = json.loads((out / "20261107T120000Z-promote-20261107T130000Z.json").read_text(encoding="utf-8"))
    assert promote["suites"]["promote-check"]["failed"] == 1
    assert not list(out.glob("*.playwright.json"))                 # downloads are not left behind
    for p in written:
        history.append(store, json.loads(p.read_text(encoding="utf-8")), None, 200)
    again, _ = vm_pull.pull("https://bucket/o/", store, tmp_path / "out2", bucket(files))
    assert again == []                                              # stored already


@pytest.mark.parametrize("change, problem", [
    ({"build": "20261107T130000Z"}, "build or step differs from its folder"),
    ({"result": "maybe"}, "no result"),
    ({"environment": {"token": "x"}}, "bad environment"),
], ids=["folder", "result", "environment"])
def test_meta_is_checked(change, problem):
    """PY-CAT-023: a release run's meta file is checked

    Given a meta file whose build differs from its folder, whose result is unknown, or whose environment has an unexpected key
    When it is checked against its folder
    Then the matching problem is reported
    """
    m = json.loads(meta(**change))
    assert problem in vm_pull.check_meta(m, "20261107T120000Z", "ui-test")


def test_bad_objects_and_outages_never_stop_the_pull(tmp_path):
    """PY-CAT-024: bad objects and outages never stop the pull

    Given a bucket with a malformed results file, a meta file that is not an object and one nested too deep
    When the release runs are pulled
    And they are pulled from a bucket that can't be reached
    And a listing's next-page token repeats
    Then from the bad objects nothing is written and three problems are reported
    And from the unreachable bucket nothing is written and the listing's OSError is the one problem
    And the repeating listing ends, with no objects
    """
    folder = "results/20261107T120000Z/ui-test-20261107T120500Z/"
    files = {folder + "meta.json": meta(), folder + "playwright.json": b'{"suites": [1]}',
             "results/20261107T120000Z/smoke-20261107T121000Z/meta.json": b"[1]",
             "results/20261107T120000Z/smoke-20261107T122000Z/meta.json": b"[" * 100_000}
    written, problems = vm_pull.pull("https://bucket/o/", tmp_path / "store", tmp_path / "out", bucket(files))
    assert written == [] and len(problems) == 3                      # each reported, none fatal

    def down(url, limit=0):
        raise OSError("connection refused")
    assert vm_pull.pull("https://bucket/o/", tmp_path / "store", tmp_path / "out", down) == ([], ["the listing: OSError"])

    pages = iter([b'{"objects": [], "nextStartWith": "a"}'] * 3)
    assert vm_pull.listing("https://bucket/o/", lambda url, limit=0: next(pages)) == []   # a repeated token ends it


def test_runs_pruned_from_the_history_are_not_fetched_again(tmp_path):
    """PY-CAT-025: runs pruned from the history are not fetched again

    Given a history that keeps one ui-test run and holds one newer than the bucket's
    When the release runs are pulled
    Then nothing is written and there is no problem
    """
    store = tmp_path / "store"
    (store / "runs/ui-test").mkdir(parents=True)
    (store / "runs/ui-test/2026-11-08T00-00-00Z_x.json").write_text("{}", encoding="utf-8")
    folder = "results/20261107T120000Z/ui-test-20261107T120500Z/"
    files = {folder + "meta.json": meta(), folder + "playwright.json": json.dumps(PLAYWRIGHT).encode()}
    assert vm_pull.pull("https://bucket/o/", store, tmp_path / "out", bucket(files), keep=1) == ([], [])
