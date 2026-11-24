"""The Selenium suite's coverage recorder (tests/selenium/page_coverage.py), with a made-up browser.

No Chrome: a stand-in driver answers the DevTools commands, so what is checked is when the coverage
is taken and what is written. Needs the `selenium` package (the Selenium lock); skipped without it.
"""

import json
import sys
from pathlib import Path

import pytest

# The package's own module: `selenium` alone would find the folder tests/selenium, which is on the
# import path, and pass without the package installed.
pytest.importorskip("selenium.webdriver")
from selenium.webdriver.remote.webdriver import WebDriver  # noqa: E402
from selenium.webdriver.remote.webelement import WebElement  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent / "selenium"))
import page_coverage  # noqa: E402

pytestmark = pytest.mark.unit

OURS = "http://127.0.0.1:1234/_astro/calculator.js"
THEIRS = "http://127.0.0.1:1234/other.js"


def browser(session: str, cdp: list):
    """A driver with no Chrome behind it: it records the DevTools commands and answers two of them."""
    d = object.__new__(WebDriver)
    d.session_id = session

    def execute_cdp_cmd(cmd, args):
        cdp.append(cmd)
        if cmd == "Profiler.takePreciseCoverage":
            return {"result": [{"url": u, "scriptId": "7", "functions": [{"ranges": []}]} for u in (OURS, THEIRS)]}
        if cmd == "Debugger.getScriptSource":
            return {"scriptSource": "let a = 1;"}
        return {}

    d.execute_cdp_cmd = execute_cdp_cmd
    return d


def test_coverage_is_taken_before_each_page_change_and_written_per_test(tmp_path, monkeypatch):
    """PY-PAGECOV-001: Each Selenium test's coverage is taken before every navigation and click, and written per test

    Given a browser recording one test's coverage and a second browser that isn't recording
    When the test opens a page, clicks, reloads and goes back, the other browser opens a page, and the test ends with a parametrized node ID
    Then the coverage is taken before each of the four, and once more at the end, in the recording browser only
    And the test's file holds its node ID without parameters and only the site's own scripts' entries
    And each script's source is fetched once and written once, beside the tests
    And after the test, opening a page takes nothing, and a test that recorded nothing writes no file
    """
    actions = []
    for cls, name in ((WebDriver, "get"), (WebDriver, "refresh"), (WebDriver, "back"), (WebElement, "click")):
        monkeypatch.setattr(cls, name, lambda self, *a, _n=name: actions.append(_n))
    monkeypatch.setattr(page_coverage, "OUT", tmp_path)
    monkeypatch.setattr(page_coverage.Recorder, "recording", {})
    page_coverage.install()

    cdp, other_cdp = [], []
    driver, other = browser("s1", cdp), browser("s2", other_cdp)
    recorder = page_coverage.Recorder(driver, "gw0-desktop")
    recorder.start()
    assert cdp == ["Profiler.enable", "Debugger.enable", "Profiler.startPreciseCoverage"]
    element = object.__new__(WebElement)
    element._parent = driver
    driver.get("http://127.0.0.1:1234/en/")
    element.click()
    driver.refresh()
    driver.back()
    other.get("http://127.0.0.1:1234/en/")
    recorder.stop("tests/selenium/test_calc.py::test_calc[en]")

    assert actions == ["get", "click", "refresh", "back", "get"]
    assert cdp.count("Profiler.takePreciseCoverage") == 5 and other_cdp == []
    assert cdp.count("Debugger.getScriptSource") == 1
    assert cdp[-3:] == ["Profiler.stopPreciseCoverage", "Debugger.disable", "Profiler.disable"]
    test = json.loads((tmp_path / "test-gw0-desktop-0001.json").read_text(encoding="utf-8"))
    assert test["node"] == "tests/selenium/test_calc.py::test_calc"
    assert len(test["entries"]) == 5 and {e["url"] for e in test["entries"]} == {OURS}
    assert "source" not in test["entries"][0]
    assert json.loads((tmp_path / "sources-gw0-desktop.json").read_text(encoding="utf-8")) == {OURS: "let a = 1;"}

    before = len(cdp)
    driver.get("http://127.0.0.1:1234/en/")
    assert len(cdp) == before  # not recording between tests
    quiet = page_coverage.Recorder(browser("s3", []), "gw1-phone")
    quiet.driver.execute_cdp_cmd = lambda cmd, args: {"result": []}
    quiet.start()
    quiet.stop("tests/selenium/test_x.py::test_x")
    assert not list(tmp_path.glob("test-gw1-*"))
