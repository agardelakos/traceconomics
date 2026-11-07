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
], ids=["none", "no-header", "order", "and-first", "stray-line"])
def test_docstring_problems(doc, problem):
    assert problem in cases_mod.from_docstring(doc)["problems"]


def test_annotations_and_meta():
    a = cases_mod.from_annotations([
        {"type": "id", "description": "PW-CALC-001"}, {"type": "given", "description": "a preset"},
        {"type": "and", "description": "English"}, {"type": "when", "description": "untouched"},
        {"type": "then", "description": "the published rate"},
        {"type": "fixme", "description": "broken in Safari, #42"}])
    assert a["id"] == "PW-CALC-001" and a["given"] == ["a preset", "English"] and a["defects"] == [42]
    m = cases_mod.from_meta({"id": "VT-FMT-001", "given": "an amount", "when": ["formatted"], "then": "€ first"})
    assert (m["id"], m["given"], m["when"], m["then"]) == ("VT-FMT-001", ["an amount"], ["formatted"], ["€ first"])


def test_issue_links():
    assert cases_mod.issues("xfail: rounding, see #12 and #7; not a/#9 or x#3") == [7, 12]


# Collecting -------------------------------------------------------------------------------------

def test_pytest_plugin_collects_outlines(tmp_path):
    """The plugin through a real pytest collection, on a throwaway test file."""
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


def test_outline_examples_must_share_steps():
    a, b = case(title="a"), case(title="b", node="tests/test_x.py::test_b", then=["other"])
    merged = collect.merge_outlines([a, b])
    assert len(merged) == 1 and any("different steps" in p for p in merged[0].problems)


# The validator ----------------------------------------------------------------------------------

def rules(catalog, strict=None, mapping=None, obsolete=(), require_all=False):
    return {(f.rule, f.error) for f in validate.check(catalog, strict or {}, mapping or {}, set(obsolete), require_all)}


def test_ratchet_warns_outside_strict_files():
    c = case(id=None, title="")
    assert rules(cat(c)) == {("missing-id", False)}
    assert rules(cat(c), strict={"files": ["tests/test_x.py"]}) == {("missing-id", True)}
    assert rules(cat(c), strict={"all": True}) == {("missing-id", True)}


def test_always_errors():
    assert ("bad-id", True) in rules(cat(case(id="PW-ENG-001")))          # another suite's prefix
    assert ("bad-id", True) in rules(cat(case(id="PY-eng-1")))
    dup = rules(cat(case(), case(file="tests/test_y.py", node="tests/test_y.py::test_a")))
    assert ("duplicate-id", True) in dup
    assert ("reused-id", True) in rules(cat(case()), obsolete={"PY-ENG-001"})
    assert ("incomplete", True) in rules(cat(case(), missing=["selenium"]), require_all=True)


def test_missing_steps():
    assert rules(cat(case(then=[])), strict={"all": True}) == {("missing-steps", True)}


def test_mapping():
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
    (tmp_path / "local.xml").write_text(JUNIT, encoding="utf-8")
    run = history.Run()
    history.read_junit(run, tmp_path / "local.xml", "pytest-local", cat(case()))
    run.finish()
    assert set(run.suites) == {"pytest-local"} and run.cases["PY-ENG-001"]["suite"] == "pytest-local"


def test_append_keeps_the_newest_and_never_forgets_an_obsolete_id(tmp_path):
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


def test_a_bad_record_is_refused(tmp_path):
    rec, _ = make_record(tmp_path)
    rec["trigger"] = "nightly"
    with pytest.raises(ValueError, match="unknown trigger"):
        history.append(tmp_path / "store", rec, None, 200)
    assert not (tmp_path / "store").exists()


# The wiki pages ---------------------------------------------------------------------------------

def test_flakiness():
    assert wiki.flakiness(["passed"] * 4) is None                      # too few
    assert wiki.flakiness(["passed"] * 6) == 0
    assert wiki.flakiness(["passed", "failed", "passed", "passed", "passed"]) == 0.5
    assert wiki.flakiness(["passed", "skipped", "passed", "passed", "passed", "passed"]) == 0


def test_pages(tmp_path):
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
    """The validator as CI calls it: isolated mode, exit code 1 on an error."""
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
    assert problems == ["results/20261107T120000Z/smoke-20261107T121000Z/: no commit"]
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
    m = json.loads(meta(**change))
    assert problem in vm_pull.check_meta(m, "20261107T120000Z", "ui-test")
