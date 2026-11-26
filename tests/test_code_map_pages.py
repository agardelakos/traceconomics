"""The wiki's code map (tests/catalog/code_map_pages.py, showcase): which tests run each line, by page.

The tests run the generator on the made-up package of tests/test_code_reference.py and a made-up
stored map; the code map's own data (tests/coverage/code_map.py) has its own tests.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "catalog"))
import code_map_pages  # noqa: E402
from test_code_reference import COMMIT, REPO, ROOT, made_up  # noqa: E402

pytestmark = pytest.mark.repository


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
    """PY-CODEREF-008: The code map's pages show each module's and member's tests, joined to their cases

    Given the made-up package, and a stored code map from an earlier commit and a catalog with unit, integration and repository cases
    When the code map is generated from that store
    Then each page names the map's commit and says it is earlier than the page's
    And each public member shows its tests per layer, or "imported only", or "no test", and a class of definitions alone shows none of them
    And each module shows its lines by status, the lines no test runs linked at the map's commit, and its cases by layer behind a summary
    And a case links to its steps on the pytest page, and a test without a case shows its node ID
    And a module newer than the map says it is not in the coverage run yet
    And each module links to its docs on the code reference
    And the overview gives each package's lines, the share run by a test and the lines no test runs
    And it lists the unit and integration tests that run no package code and the test runs without a case, not the repository checks
    """
    out = tmp_path / "wiki"
    code_map_pages.generate(made_up(tmp_path), out, REPO, COMMIT, store(tmp_path))
    top = (out / "Code-map-top-level.md").read_text(encoding="utf-8")
    assert f"coverage of commit [`fedcba9`](https://github.com/{REPO}/commit/{MAP_COMMIT})" in top
    assert "an earlier commit than this page's" in top
    assert "- `run` · tests: unit 1" in top
    assert "  - `take` · tests: integration 1" in top
    assert "[docs](Code-top-level#traceconomicsjob)" in top
    assert (
        "**Tests:** 6 lines with code: run by unit tests 2, by integration tests only 1, imported only 2, no test 1 "
        f"(lines [12–13](https://github.com/{REPO}/blob/{MAP_COMMIT}/src/traceconomics/job.py#L12-L13))."
    ) in top
    assert "<details><summary>Test cases that run it: unit 1, integration 2</summary>" in top
    assert "Unit:\n\n- [PY-JOB-001](Tests-pytest#py-job-001) The job runs" in top
    assert (
        "- [PY-LOCK-001](Tests-pytest#py-lock-001) The lock is taken\n- `tests/test_orphan.py::test_x` (no case)" in top
    )
    engine = (out / "Code-map-engine.md").read_text(encoding="utf-8")
    assert "- `link` · **imported only**" in engine and "- `spare` · **no test**" in engine
    assert "- class `Point`\n" in engine  # definitions only: nothing a test could run
    assert "_Not in the coverage run yet: the module is newer than the code map._" in engine
    overview = (out / "Code-map.md").read_text(encoding="utf-8")
    assert "| Lines with code | Run by a test | Imported only | No test |" in overview
    assert "| 6 | 3 (50%) | 2 (33%) | 1 (17%) |" in overview  # the top-level modules' row
    assert "Checks on the code itself" not in overview and "PY-DOCS-001" not in overview
    assert "- [PY-HELP-001](Tests-pytest#py-help-001) A helper under tests (unit)" in overview
    assert "## Test runs without a case\n\n- `tests/test_orphan.py::test_x`" in overview
    assert "PW-X-001" not in overview


def test_the_charts_are_self_contained_svg_in_light_and_dark():
    """PY-CODEREF-010: The charts are self-contained SVG, light and dark, with bars that add up and cells that say their share

    Given stacked-bar rows under a heading, and heatmap rows with a share of none, a small share, all, and one not measured
    When each chart is drawn in light and dark, twice
    Then each SVG parses, names its title, and refers to no script, link or other site
    And the legend lists only the statuses in the rows, and each bar's segments together are as long as its total
    And each heatmap cell shows its share, "<1%" for a small one and "–" where not measured, with the "not measured" key
    And the light and dark versions differ only in colour, and drawing again gives the same bytes
    """
    import xml.etree.ElementTree as ET

    sys.path.insert(0, str(ROOT / "tests" / "catalog"))
    import code_charts as charts

    ns = {"s": "http://www.w3.org/2000/svg"}
    rows = [("#", "Back end"), ("engine", {"unit": 30, "imported": 10}), ("store", {"integration": 5, "none": 15})]
    bars = charts.pair("code-map-x", lambda th: charts.bars(rows, "Lines per area", th))
    assert sorted(bars) == ["code-map-x-dark.svg", "code-map-x-light.svg"]
    for text in bars.values():
        root = ET.fromstring(text)
        assert root.find("s:title", ns).text == "Lines per area"
        assert "<script" not in text and "href" not in text and "http" not in text.replace(ns["s"], "")
        legend = [t.text for t in root.iterfind("s:text", ns)][1:5]
        assert legend == ["unit", "integration", "imported", "none"]
    light = ET.fromstring(bars["code-map-x-light.svg"])
    engine = next(g for g in light.iterfind("s:g", ns) if g.find("s:title", ns).text.startswith("engine"))
    assert engine.find("s:title", ns).text == "engine: 40 lines; unit 30, imported 10"
    store = next(g for g in light.iterfind("s:g", ns) if g.find("s:title", ns).text.startswith("store"))
    # Each bar ends at its total's label: 20 lines against engine's 40 reach half as far from the axis.
    x0 = 16 + 200  # the left padding and the label column

    def end(g):
        return float([t for t in g.iterfind("s:text", ns)][-1].get("x")) - 6 - x0

    assert abs(end(store) - end(engine) / 2) < 0.5
    assert bars == charts.pair("code-map-x", lambda th: charts.bars(rows, "Lines per area", th))
    assert bars["code-map-x-light.svg"] != bars["code-map-x-dark.svg"]

    heat = charts.heatmap(
        [("lib", {"a": 0, "b": 0.004}), ("pages", {"a": 1.0, "b": None})], ["a", "b"], "Share", charts.THEMES["light"]
    )
    cells = [t.text for t in ET.fromstring(heat).iterfind(".//s:g/s:text", ns)]
    assert cells == ["0", "<1%", "100%", "–"] and "not measured" in heat


def front_store(tmp_path: Path, *, selenium: bool = True) -> Path:
    """The stored map of store(), with "ran" counts and a front end of two site files."""
    folder = store(tmp_path)
    m = json.loads((folder / "code-map.json").read_text(encoding="utf-8"))
    for e in m["back-end"]["modules"].values():
        e["ran"] = {"unit": e["unit"], "integration": e["integration"]}
    keys = [
        "playwright|PW-CALC-001",
        "selenium|tests/selenium/test_calc.py::test_calc",
        "vitest|src/lib/x.test.ts",
        "vitest|src/lib/y.test.ts",
    ]

    def site_entry(lines, unit, e2e, none, tests, ran, pw_only, sel_only, no_test=()):
        return {
            "lines": lines,
            "unit": unit,
            "integration": 0,
            "e2e": e2e,
            "none": none,
            "no_test": [list(r) for r in no_test],
            "tests": tests,
            "ran": ran if selenium else {**ran, "selenium": None},
            "playwright_only": pw_only if selenium else None,
            "selenium_only": sel_only if selenium else None,
        }

    m["front-end"] = {
        "tests": keys,
        "selenium": selenium,
        "files": {
            "src/lib/x.ts": site_entry(
                10,
                8,
                1,
                1,
                {"unit": [2, 3], "integration": [], "e2e": [0], "selenium": [1]},
                {"unit": 8, "integration": 0, "e2e": 3, "selenium": 2},
                [[4, 4]],
                [],
                no_test=[(9, 9)],
            ),
            "src/scripts/y.ts": site_entry(
                4,
                0,
                4,
                0,
                {"unit": [], "integration": [], "e2e": [0], "selenium": [1]},
                {"unit": 0, "integration": 0, "e2e": 4, "selenium": 4},
                [],
                [],
            ),
        },
    }
    (folder / "code-map.json").write_text(json.dumps(m), encoding="utf-8")
    cat = json.loads((folder / "catalog.json").read_text(encoding="utf-8"))
    cat["cases"] += [
        {"id": "VT-X-001", "suite": "vitest", "node": "x", "title": "x formats", "file": "site/src/lib/x.test.ts"},
        {"id": "PW-CALC-001", "suite": "playwright", "node": "c", "title": "The calculator opens", "file": "c"},
    ]
    (folder / "catalog.json").write_text(json.dumps(cat), encoding="utf-8")
    return folder


def test_the_pages_show_the_charts_and_the_front_end(tmp_path):
    """PY-CODEREF-011: With a front end in the map, the pages show the charts, the site's own page and the two browser suites compared

    Given the made-up package, a stored map with a front end of two site files run by Vitest, Playwright and Selenium, and a wiki folder with an old chart and another picture
    When the code map is generated, then again from a map without Selenium's lines
    Then the overview has the map's legend, the bars and both heatmaps, each with a table, and the browser suites compared by folder
    And every chart a page shows is written, in light and dark, and parses as XML; the old chart is removed and the other picture stays
    And the site's page has a chart per folder, each file's lines, its tests linked to their cases (a Vitest file's every case, a test without a case by name), and the lines only one browser suite runs
    And the sidebar's code-map block lists the overview, each package's page and the site's page, and the code reference's block is left alone
    And without Selenium's lines both pages say it wasn't measured
    """
    out = tmp_path / "wiki"
    out.mkdir()
    (out / "code-map-old-light.svg").write_text("old", encoding="utf-8")
    (out / "logo.svg").write_text("kept", encoding="utf-8")
    sidebar = (
        "- [Home](Home)\n  <!-- code:start -->\n  <!-- code:end -->\n\n**Testing**\n\n- [Tests](Tests)\n"
        "  <!-- codemap:start -->\n  <!-- codemap:end -->\n"
    )
    (out / "_Sidebar.md").write_text(sidebar, encoding="utf-8")
    code_map_pages.generate(made_up(tmp_path), out, REPO, COMMIT, front_store(tmp_path))
    overview = (out / "Code-map.md").read_text(encoding="utf-8")
    for part in (
        "## The map",
        "| **imported** | dark grey |",
        'srcset="code-map-overview-dark.svg"',
        "code-map-heat-back-light.svg",
        "code-map-heat-front-light.svg",
        "| Front end | Lines | unit | integration | e2e | none |",
        "| Folder | Lines | Playwright runs, Selenium doesn't | Selenium runs, Playwright doesn't |",
        "| lib | 10 | 1 | 0 |",
    ):
        assert part in overview, part
    shown = set()
    for page in out.glob("Code*.md"):
        shown |= set(re.findall(r'(?:src|srcset)="(code-map-[^"]+\.svg)"', page.read_text(encoding="utf-8")))
    assert shown and all((out / name).is_file() for name in shown)
    import xml.etree.ElementTree as ET

    for svg in out.glob("code-map-*.svg"):
        ET.fromstring(svg.read_text(encoding="utf-8"))  # GitHub shows an SVG only if it is well formed
    assert {n.replace("-light", "-dark") for n in shown if "-light" in n} <= shown
    assert not (out / "code-map-old-light.svg").exists() and (out / "logo.svg").read_text(encoding="utf-8") == "kept"
    site = (out / "Code-map-site.md").read_text(encoding="utf-8")
    for part in (
        "## lib",
        'src="code-map-site-scripts-light.svg"',
        "### `src/lib/x.ts`",
        "**Tests:** 10 lines with code: unit 8, integration 0, e2e 1, none 1 (no test: lines [9](",
        "<details><summary>Tests that run it: Vitest unit 2, Playwright 1, Selenium 1</summary>",
        "- `src/lib/x.test.ts`: [VT-X-001](Tests-Vitest#vt-x-001) x formats",
        "- `src/lib/y.test.ts` (no case)",
        "- [PW-CALC-001](Tests-Playwright#pw-calc-001) The calculator opens",
        "- `tests/selenium/test_calc.py::test_calc` (no case)",
        f"| `src/lib/x.ts` | 1: [4](https://github.com/{REPO}/blob/{MAP_COMMIT}/site/src/lib/x.ts#L4) |  |",
    ):
        assert part in site, part
    side = (out / "_Sidebar.md").read_text(encoding="utf-8")
    reference, testing = side.split("**Testing**")
    assert reference == "- [Home](Home)\n  <!-- code:start -->\n  <!-- code:end -->\n\n"
    assert (
        "- [Tests](Tests)\n  <!-- codemap:start -->\n- [Code map](Code-map)\n  - [Top-level modules](Code-map-top-level)\n"
        "  - [engine](Code-map-engine)\n  - [Front end (site)](Code-map-site)\n  <!-- codemap:end -->"
    ) in testing

    again = tmp_path / "again"
    code_map_pages.generate(made_up(tmp_path / "b"), again, REPO, COMMIT, front_store(tmp_path / "b", selenium=False))
    assert "Not measured in this run" in (again / "Code-map.md").read_text(encoding="utf-8")
    assert "Not measured in this run" in (again / "Code-map-site.md").read_text(encoding="utf-8")


def test_the_engine_page_shows_the_mutation_result(tmp_path):
    """PY-CODEREF-012: The engine's page ends with the mutation testing result in brief, linked to its own page

    Given the made-up package, a stored code map and a mutation result with two survivors, one listed as behaving the same with its reason
    When the code map is generated, then again after the engine's source changed, then from a result with no survivors
    Then the engine's page gives the score, the changes, the date and the commit, the survivors and how many aren't explained yet
    And it links to the mutation testing page for the changes, the survivors and the score over time
    And no other page shows the result
    And once the engine's source has changed, the page says the result may no longer hold
    And with no survivors it says none survived
    """
    src = made_up(tmp_path)
    sys.path.insert(0, str(ROOT / "tests" / "coverage"))
    import mutation

    folder = store(tmp_path)  # the map the pages are made from, with the mutation result beside it
    survivors = [
        {"mutant": "m1", "function": "traceconomics.engine.chain.link", "change": ["-    continue", "+    break"]},
        {"mutant": "m2", "function": "traceconomics.engine.chain.link", "change": ["-    a = 1", "+    a = 2"]},
    ]
    result = {
        "schema": 1,
        "commit": MAP_COMMIT,
        "mutants": 10,
        "counts": {"killed": 8, "survived": 2},
        "score": 80.0,
        "started": "2026-12-08T10:00:00Z",
        "survivors": survivors,
        "source": mutation.fingerprint(tmp_path),
    }
    (folder / "mutation.json").write_text(json.dumps(result), encoding="utf-8")
    known = tmp_path / "tests" / "coverage" / "mutation-equivalent.toml"
    known.parent.mkdir(parents=True)
    known.write_text(
        '[[equivalent]]\nfunction = "traceconomics.engine.chain.link"\n'
        'change = ["-  a = 1", "+  a = 2"]\nreason = "a is never read."\n',
        encoding="utf-8",
    )
    out = tmp_path / "wiki"
    code_map_pages.generate(src, out, REPO, COMMIT, folder)
    engine = (out / "Code-map-engine.md").read_text(encoding="utf-8")
    assert (
        f"## Mutation testing\n\n**80.0%** of 10 changes to the engine's code killed by its tests, on 2026-12-08 "
        f"(commit [`fedcba9`](https://github.com/{REPO}/commit/{MAP_COMMIT})); 2 survived, 1 not explained yet. "
        "Every change, every survivor and the score over time: [Mutation testing](Tests-Mutation)."
    ) in engine
    assert "may no longer hold" not in engine and "```diff" not in engine
    assert all(
        "Mutation testing" not in p.read_text(encoding="utf-8")
        for p in out.glob("Code*.md")
        if p.name != "Code-map-engine.md"
    )

    (src / "engine" / "chain.py").write_text("# changed\n", encoding="utf-8")
    code_map_pages.generate(src, out, REPO, COMMIT, folder)
    assert "may no longer hold" in (out / "Code-map-engine.md").read_text(encoding="utf-8")

    result |= {"counts": {"killed": 10}, "score": 100.0, "survivors": []}
    (folder / "mutation.json").write_text(json.dumps(result), encoding="utf-8")
    code_map_pages.generate(src, out, REPO, COMMIT, folder)
    assert "killed by its tests, on 2026-12-08 (commit" in (out / "Code-map-engine.md").read_text(encoding="utf-8")
    assert "none survived." in (out / "Code-map-engine.md").read_text(encoding="utf-8")


def test_without_a_map_no_page_is_written_and_old_ones_go(tmp_path):
    """PY-CODEREF-013: Without a stored code map no page is written, the map's old pages go, and other pages stay

    Given a wiki folder with an old code-map page and chart, a code reference page, and a sidebar with the code map's block filled
    When the code map is generated from a store holding no map, from the command line
    Then it says nothing was written
    And the old code-map page and chart are gone, the code reference page stays, and the sidebar's block is empty
    """
    out = tmp_path / "wiki"
    out.mkdir()
    for name in ("Code-map.md", "Code-map-engine.md", "code-map-overview-light.svg", "Code-engine.md"):
        (out / name).write_text("old\n", encoding="utf-8")
    (out / "_Sidebar.md").write_text(
        "- [Home](Home)\n  <!-- codemap:start -->\n- [Code map](Code-map)\n  <!-- codemap:end -->\n", encoding="utf-8"
    )
    empty = tmp_path / "store"
    empty.mkdir()
    script = ROOT / "tests" / "catalog" / "code_map_pages.py"
    args = [
        "--src",
        str(made_up(tmp_path)),
        "--out",
        str(out),
        "--repo",
        REPO,
        "--commit",
        COMMIT,
        "--store",
        str(empty),
    ]
    done = subprocess.run([sys.executable, "-I", str(script), *args], capture_output=True, text=True)
    assert done.returncode == 0 and "nothing: no code map stored" in done.stdout
    assert sorted(p.name for p in out.iterdir()) == ["Code-engine.md", "_Sidebar.md"]
    assert (out / "_Sidebar.md").read_text(encoding="utf-8") == (
        "- [Home](Home)\n  <!-- codemap:start -->\n  <!-- codemap:end -->\n"
    )
