"""Each Selenium test's coverage of the site's scripts, for the wiki's code map: off unless asked for.

On with TRACECONOMICS_COVERAGE=on and TRACECONOMICS_CODE_MAP=on, against a coverage build of the
site (`TRACECONOMICS_COVERAGE=on npm run build`: its scripts carry source maps). Chrome's profiler
(the DevTools protocol, as Playwright uses it) records which parts of each script ran; site/scripts/
code-map-lines.mjs turns that into source lines afterwards, the same way as Playwright's.

Chrome keeps a page's coverage only while the page is open, so it is taken before every navigation
(`get`, `refresh`) and every click, as the Playwright fixture's `coverage.flush()` does. The profiler
has to start on a page of the site's own origin: started on `about:blank`, it is lost when the first
page of the site opens in another renderer. So it starts on the test server's blank page
(server.BLANK), and only when the suite serves the build itself, not with `--base-url`.

Writes site/coverage/selenium-pertest/: per test, `test-<worker>-<n>.json` (its node ID and the
raw entries), and per Chrome, `sources-<worker>-<kind>.json` (each script's source, once).
"""

from __future__ import annotations

import json
import os
import re
import shutil

from helpers import DIST
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

ON = os.environ.get("TRACECONOMICS_COVERAGE") == "on" and os.environ.get("TRACECONOMICS_CODE_MAP") == "on"
OUT = DIST.parent / "coverage" / "selenium-pertest"
OURS = "/_astro/"  # the site's own scripts, as the Playwright fixture keeps them


class Recorder:
    """One Chrome's profiler: started for a test, taken before each navigation and click, saved after."""

    recording: dict[str, Recorder] = {}  # by the driver's session

    def __init__(self, driver: WebDriver, name: str):
        self.driver, self.name = driver, name
        self.entries: list[dict] = []
        self.sources: dict[str, str] = {}
        self.count = 0

    def start(self):
        self.entries = []
        self.driver.execute_cdp_cmd("Profiler.enable", {})
        self.driver.execute_cdp_cmd("Debugger.enable", {})
        self.driver.execute_cdp_cmd("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True})
        Recorder.recording[self.driver.session_id] = self

    def take(self):
        """What ran since the last take, with the source of any script not seen before."""
        result = self.driver.execute_cdp_cmd("Profiler.takePreciseCoverage", {})["result"]
        for script in result:
            if OURS not in script["url"]:
                continue
            if script["url"] not in self.sources:
                source = self.driver.execute_cdp_cmd("Debugger.getScriptSource", {"scriptId": script["scriptId"]})
                self.sources[script["url"]] = source["scriptSource"]
            self.entries.append(
                {"url": script["url"], "scriptId": script["scriptId"], "functions": script["functions"]}
            )

    def stop(self, node: str):
        """The test's last coverage, then its file; the profiler stops until the next test."""
        Recorder.recording.pop(self.driver.session_id, None)
        try:
            self.take()
        finally:
            self.driver.execute_cdp_cmd("Profiler.stopPreciseCoverage", {})
            self.driver.execute_cdp_cmd("Debugger.disable", {})
            self.driver.execute_cdp_cmd("Profiler.disable", {})
        if not self.entries:
            return
        OUT.mkdir(parents=True, exist_ok=True)
        self.count += 1
        test = {"node": re.sub(r"\[.*\]$", "", node), "entries": self.entries}
        (OUT / f"test-{self.name}-{self.count:04d}.json").write_text(json.dumps(test), encoding="utf-8")
        (OUT / f"sources-{self.name}.json").write_text(json.dumps(self.sources), encoding="utf-8")


def _before(method):
    """`method`, after taking the coverage of the page it may leave, when its Chrome is recording."""

    def wrapped(self, *args, **kwargs):
        driver = self._parent if isinstance(self, WebElement) else self
        recorder = Recorder.recording.get(driver.session_id)
        if recorder is not None:
            recorder.take()
        return method(self, *args, **kwargs)

    return wrapped


def install():
    """Take the coverage before every navigation and click, in every Chrome of this process."""
    WebDriver.get = _before(WebDriver.get)
    WebDriver.refresh = _before(WebDriver.refresh)
    WebDriver.back = _before(WebDriver.back)
    WebElement.click = _before(WebElement.click)


def clear():
    """The previous run's files go: the map is this run's alone."""
    shutil.rmtree(OUT, ignore_errors=True)
