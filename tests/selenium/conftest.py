"""Shared fixtures for the Selenium browser tests.

Run them with `pytest tests/selenium --selenium` (add `-n auto` for one Chrome per CPU) after
building the site (`npm run build` in site/). They serve `site/dist` from this process, unless
`--base-url` points them at another server (the `host` tests need one that applies the site's
headers, such as `npx wrangler dev`).

Chrome is Chrome for Testing at one pinned version, fetched by Selenium Manager into
~/.cache/selenium on first use, so every machine and CI run uses the same browser.

One Chrome per worker is kept for the whole run and reset between tests (storage, cookies,
emulation, logs), because starting Chrome for every test would cost about a second each. The
phone and no-script browsers are separate Chromes, started the first time a test asks for one.

After every test the browser's console must hold no error; a test that expects one says so with
`@pytest.mark.console_errors`. A failing test leaves a screenshot, the page's HTML and the console
in site/selenium-report/failures/.
"""

import json
import re
import shutil
from pathlib import Path

import pytest
from selenium import webdriver

from helpers import DIST, REPORT, Site
from server import StaticServer

# Chrome for Testing 156.0.8078.47, published 2026-10-19 (at least two weeks before it was pinned).
CHROME_VERSION = "156.0.8078.47"

BLOCKED = ["*cloudflareinsights.com*"]
DESKTOP = (1280, 900)
# Pixel 7, as Chrome's device list has it.
PHONE = {"deviceMetrics": {"width": 412, "height": 915, "pixelRatio": 2.625, "touch": True, "mobile": True},
         "userAgent": "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/156.0.0.0 Mobile Safari/537.36"}


def pytest_configure(config):
    config.addinivalue_line("markers", "console_errors: the test expects errors in the browser's console")
    config.addinivalue_line("markers", "phone: the test uses the phone browser")


def pytest_sessionstart(session):
    # Failure reports are for this run only. Under xdist only the controller clears them, before
    # any worker starts.
    if not hasattr(session.config, "workerinput"):
        shutil.rmtree(REPORT / "failures", ignore_errors=True)


def _options(*, phone=False, scripts=True) -> webdriver.ChromeOptions:
    o = webdriver.ChromeOptions()
    o.browser_version = CHROME_VERSION
    o.add_argument("--headless=new")
    o.add_argument("--no-first-run")
    o.add_argument("--disable-search-engine-choice-screen")
    o.add_argument("--lang=en-GB")
    o.add_experimental_option("prefs", {"intl.accept_languages": "en-GB,en",
                                        **({} if scripts else {"profile.managed_default_content_settings.javascript": 2})})
    o.set_capability("goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"})
    if phone:
        o.add_experimental_option("mobileEmulation", PHONE)
    else:
        o.add_argument(f"--window-size={DESKTOP[0]},{DESKTOP[1]}")
        # Headless Chrome reports no pointer at all ("hover: none"), unlike a desktop with a mouse,
        # and the site's mouse-only behaviour (terms open on hover) would never run.
        o.add_argument("--blink-settings=primaryHoverType=2,availableHoverTypes=2,primaryPointerType=4,availablePointerTypes=4")
    return o


class _Pool:
    """The worker's Chromes, started when first asked for, closed at the end of the run."""

    def __init__(self):
        self._drivers: dict[str, webdriver.Chrome] = {}

    def get(self, kind: str) -> webdriver.Chrome:
        if kind not in self._drivers:
            d = webdriver.Chrome(options=_options(phone=kind == "phone", scripts=kind != "noscript"))
            d.set_page_load_timeout(30)
            d.execute_cdp_cmd("Network.enable", {})
            self._drivers[kind] = d
        return self._drivers[kind]

    def close(self):
        for d in self._drivers.values():
            d.quit()


@pytest.fixture(scope="session")
def base_url(request):
    given = request.config.getoption("--base-url")
    if given:
        yield given.rstrip("/")
        return
    try:
        server = StaticServer(DIST)
    except FileNotFoundError as e:
        pytest.exit(str(e), returncode=4)
    with server:
        yield server.url


@pytest.fixture(scope="session")
def _pool():
    pool = _Pool()
    yield pool
    pool.close()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    setattr(item, f"_report_{report.when}", report)
    return report


def _reset(driver, base_url):
    """Back to a blank page with nothing stored, as a new visitor."""
    driver.get("about:blank")
    origin = re.match(r"https?://[^/]+", base_url)[0]
    driver.execute_cdp_cmd("Storage.clearDataForOrigin", {"origin": origin, "storageTypes": "all"})
    driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
    # The analytics beacon is only in release builds; if one ever sneaks into a test build it must
    # not reach Cloudflare. (Set on every reset: a test may block more, to see a page fail.)
    driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": BLOCKED})
    driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": ""}]})
    for kind in ("browser", "performance"):
        driver.get_log(kind)


def _save_failure(item, site: Site, console: list[dict]):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", item.nodeid.split("tests/selenium/")[-1])[:150]
    out = REPORT / "failures" / name
    out.mkdir(parents=True, exist_ok=True)
    d = site.driver
    try:
        d.save_screenshot(str(out / "screenshot.png"))
        (out / "page.html").write_text(d.page_source, encoding="utf-8", newline="\n")
        (out / "url.txt").write_text(d.current_url + "\n", encoding="utf-8", newline="\n")
    except Exception as e:  # a broken page must not hide the test's own failure
        (out / "capture-error.txt").write_text(repr(e) + "\n", encoding="utf-8", newline="\n")
    (out / "console.json").write_text(json.dumps(console, indent=1, ensure_ascii=False) + "\n",
                                      encoding="utf-8", newline="\n")


def _site_fixture(kind):
    @pytest.fixture
    def fixture(request, _pool, base_url):
        driver = _pool.get(kind)
        _reset(driver, base_url)
        site = Site(driver, base_url, phone=kind == "phone")
        yield site
        console = site.console()
        call = getattr(request.node, "_report_call", None)
        if call is not None and call.failed:
            _save_failure(request.node, site, console)
        errors = [e for e in console if e["level"] == "SEVERE"]
        if errors and not request.node.get_closest_marker("console_errors") and (call is None or call.passed):
            pytest.fail("errors in the browser's console:\n" + "\n".join(e["message"] for e in errors), pytrace=False)
    return fixture


site = _site_fixture("desktop")
phone = _site_fixture("phone")
noscript = _site_fixture("noscript")


@pytest.fixture
def host_url(request):
    """The tests of the host's own headers need a real host, not the test process's server."""
    given = request.config.getoption("--base-url")
    if not given:
        pytest.skip("needs --base-url: a server that applies the site's headers (npx wrangler dev)")
    return given.rstrip("/")
