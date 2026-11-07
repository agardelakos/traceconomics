"""What the Selenium tests share: the site's texts and data files, number formats, and `Site`, a
thin layer over WebDriver with explicit waits (no sleeps, no retries).

Expected values come from the files the pages are built from: the texts in site/src/i18n, the
exported JSON in site/dist/data. The tests check that a page shows what the files say, not that
the files are right (the Python tests and the site's own unit tests do that).
"""

import json
import math
import re
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

from selenium.common.exceptions import JavascriptException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
DIST = SITE / "dist"
REPORT = SITE / "selenium-report"
M1 = "data/v1/gr/m1/latest"
WAIT = 10  # seconds; a page of this site that takes longer than this is broken
# Addresses every test blocks: the visit counter, only in release builds, must never be reached.
BLOCKED = ["*cloudflareinsights.com*"]
NNBSP = "\u202f"  # narrow no-break space: the site's thousands mark in both languages


# --- texts and numbers, as the site writes them -------------------------------------------------

@cache
def _texts(lang: str) -> dict[str, str]:
    return json.loads((SITE / "src" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))


def t(lang: str, key: str, **values) -> str:
    """A text of the site, its {slots} filled; a missing slot is an error, as on the site."""
    text = _texts(lang)[key]

    def slot(m):
        if m[1] not in values:
            raise KeyError(f"text {key!r} needs {{{m[1]}}}")
        return str(values[m[1]])
    return re.sub(r"\{(\w+)\}", slot, text)


def num(lang: str, value: float, digits: int = 1) -> str:
    """5.1 or 5,1; thousands split by a narrow no-break space; never "-0.0"."""
    text = f"{abs(value):,.{digits}f}".replace(",", NNBSP)
    if lang == "el":
        text = text.replace(".", ",")
    negative = value < 0 and float(f"{value:.{digits}f}") != 0
    return ("-" if negative else "") + text


# JavaScript's rounding, not Python's: round() goes to the even number on a tie (592.5 -> 592),
# the site's toFixed(0) and Math.round go up (593).

def js_round(value: float) -> int:
    """Math.round: ties towards +infinity."""
    return math.floor(value + 0.5)


def _fixed0(value: float) -> int:
    """Number.toFixed(0) on a non-negative number: ties away from zero, on the exact binary value."""
    return int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def household_type(older: int, children: int, older_dependents: int) -> str | None:
    """Eurostat's household type: one, two, three or more adults; _DCH with dependent children.
    None when nobody is an adult."""
    dependents = min(older_dependents, older)
    adults = older - dependents
    if adults < 1:
        return None
    base = "A1" if adults == 1 else "A2" if adults == 2 else "A_GE3"
    return base + ("_DCH" if children + dependents > 0 else "")


def pct(lang: str, value: float, digits: int = 1) -> str:
    """A percentage as the site writes it (format.ts `pct`): the number, then "%"."""
    return f"{num(lang, value, digits)}%"


def eur(value: float) -> str:
    grouped = f"{_fixed0(abs(value)):,d}".replace(",", NNBSP)
    return ("\u2212\u20ac" if value < 0 else "\u20ac") + grouped


def pps(value: float) -> str:
    return f"{_fixed0(abs(value)):,d}".replace(",", NNBSP) + "\u00a0PPS"


EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"]
EL_MONTHS = {
    "nom": ["Ιανουάριος", "Φεβρουάριος", "Μάρτιος", "Απρίλιος", "Μάιος", "Ιούνιος", "Ιούλιος", "Αύγουστος",
            "Σεπτέμβριος", "Οκτώβριος", "Νοέμβριος", "Δεκέμβριος"],
    "acc": ["Ιανουάριο", "Φεβρουάριο", "Μάρτιο", "Απρίλιο", "Μάιο", "Ιούνιο", "Ιούλιο", "Αύγουστο",
            "Σεπτέμβριο", "Οκτώβριο", "Νοέμβριο", "Δεκέμβριο"],
}


def month(lang: str, period: str, form: str = "nom") -> str:
    year, m = period[:4], int(period[5:7]) - 1
    return f"{EL_MONTHS[form][m] if lang == 'el' else EN_MONTHS[m]} {year}"


# --- data files ---------------------------------------------------------------------------------

@cache
def data(rel: str):
    """An exported JSON file, by its path under the m1 folder (e.g. "settings.json")."""
    return json.loads((DIST / M1 / rel).read_text(encoding="utf-8"))


def cutoffs(source: str = "ours") -> dict:
    """One source's income limits from the exported file: "ours" (the page's first) or "eurostat"."""
    return data("income-limits.json")[source]


def default_slug() -> str:
    return data("settings.json")["default"]


def latest(values: list) -> tuple[int, float]:
    """The last month with a value: its position and the value."""
    i = len(values) - 1
    while i > 0 and values[i] is None:
        i -= 1
    return i, values[i]


def months(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while (p := f"{y}-{m:02d}") <= end:
        out.append(p)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


@cache
def sitemap_paths() -> list[str]:
    """The pages the sitemap lists (the offered languages), as paths ("/en/about/")."""
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    tree = ElementTree.parse(DIST / "sitemap.xml")
    return [urlsplit(loc.text).path for loc in tree.getroot().iterfind("s:url/s:loc", ns)]


# Income fifths, as the finder and the income panel compute them (the modified OECD scale).

def equivalent_size(older: int, children: int) -> float:
    return round(10 + 5 * (older - 1) + 3 * children) / 10


def place_income(cuts: dict, size: float, yearly: float) -> tuple[str, str | None]:
    """The fifth an income falls in, and the neighbouring fifth when it is within 5% of a limit."""
    fifths = ["Q1", "Q2", "Q3", "Q4", "Q5"]
    tops = [cuts[q] for q in fifths[:4]]
    e = yearly / size
    at = next((i for i, c in enumerate(tops) if e <= c), 4)
    near = sorted((abs(e - tops[k]) / tops[k], k) for k in (at - 1, at) if 0 <= k < 4 and abs(e - tops[k]) / tops[k] <= 0.05)
    neighbour = None
    if near:
        k = near[0][1]
        neighbour = fifths[at + 1 if k == at else at - 1]
    return fifths[at], neighbour


# --- the browser --------------------------------------------------------------------------------

class Site:
    """One browser on the site: addresses relative to the base, waits, the console, requests."""

    def __init__(self, driver, base_url: str, *, phone: bool = False):
        self.driver = driver
        self.base = base_url
        self.phone = phone
        self._console: list[dict] = []
        self._requests: list[dict] = []

    # Navigation.
    def open(self, path: str):
        self.driver.get(self.base + path)
        self.wait(lambda d: d.execute_script("return document.readyState") == "complete")
        return self

    def reload(self):
        self.driver.refresh()
        self.wait(lambda d: d.execute_script("return document.readyState") == "complete")

    @property
    def path(self) -> str:
        return urlsplit(self.driver.current_url).path

    @property
    def query(self) -> dict[str, str]:
        return {k: v[0] for k, v in parse_qs(urlsplit(self.driver.current_url).query).items()}

    # Finding things.
    def find(self, css: str, within: WebElement | None = None) -> WebElement:
        return (within or self.driver).find_element(By.CSS_SELECTOR, css)

    def all(self, css: str, within: WebElement | None = None) -> list[WebElement]:
        return (within or self.driver).find_elements(By.CSS_SELECTOR, css)

    def js(self, script: str, *args):
        return self.driver.execute_script(script, *args)

    # Waiting: every check that depends on a script polls until it holds or WAIT runs out.
    def wait(self, condition, message: str = "", timeout: float = WAIT):
        return WebDriverWait(self.driver, timeout, ignored_exceptions=[StaleElementReferenceException]).until(condition, message)

    def visible(self, css: str) -> WebElement:
        return self.wait(lambda d: next((e for e in d.find_elements(By.CSS_SELECTOR, css) if e.is_displayed()), False),
                         f"{css} never became visible")

    def hidden(self, css: str):
        self.wait(lambda d: all(not e.is_displayed() for e in d.find_elements(By.CSS_SELECTOR, css)),
                  f"{css} stayed visible")

    def text(self, css: str, expected: str) -> WebElement:
        """Waits until the element's text is `expected`; the message shows what it was instead."""
        seen = []

        def check(d):
            el = d.find_element(By.CSS_SELECTOR, css)
            seen[:] = [el.text]
            return el if el.text == expected else False
        try:
            return self.wait(check)
        except Exception:
            raise AssertionError(f"{css}: text {seen[0] if seen else None!r}, expected {expected!r}") from None

    def attr(self, css: str, name: str, expected: str | None):
        seen = []

        def check(d):
            v = d.find_element(By.CSS_SELECTOR, css).get_attribute(name)
            seen[:] = [v]
            return v == expected
        try:
            self.wait(check)
        except Exception:
            raise AssertionError(f"{css}[{name}]: {seen[0] if seen else None!r}, expected {expected!r}") from None

    def url_has(self, **params):
        """Waits until the address carries exactly these values (None: the parameter is absent)."""
        def check(_):
            q = self.query
            return all(q.get(k) == v for k, v in params.items())
        try:
            self.wait(check)
        except Exception:
            raise AssertionError(f"address {self.driver.current_url}, expected {params}") from None

    def popover_open(self, el: WebElement) -> bool:
        return self.js("return arguments[0].matches(':popover-open')", el)

    def scripts_ran(self, css: str):
        """A script-built element exists and the script has run (its first child is drawn)."""
        self.wait(lambda d: d.execute_script("const e = document.querySelector(arguments[0]); return !!e && e.childElementCount > 0", css),
                  f"{css} was never drawn")

    # What the browser saw: console entries and network requests since the test began.
    def console(self) -> list[dict]:
        self._console += self.driver.get_log("browser")
        return self._console

    def requests(self) -> list[dict]:
        """Each request the page sent: url, method and body, from Chrome's performance log."""
        for entry in self.driver.get_log("performance"):
            msg = json.loads(entry["message"])["message"]
            if msg["method"] == "Network.requestWillBeSent":
                r = msg["params"]["request"]
                self._requests.append({"url": r["url"], "method": r["method"], "body": r.get("postData", "")})
        return self._requests

    def storage(self) -> dict[str, str]:
        try:
            return self.js("return Object.fromEntries(Object.entries(localStorage))")
        except JavascriptException:
            return {}

    # Accessibility, with axe-core from the site's own dev dependencies.
    def axe(self, impacts=("serious", "critical")) -> list[dict]:
        source = SITE / "node_modules" / "axe-core" / "axe.min.js"
        if not source.is_file():
            raise FileNotFoundError(f"{source} is missing: run `npm ci` in site/")
        if not self.js("return typeof window.axe === 'object'"):
            self.js(source.read_text(encoding="utf-8"))
        result = self.driver.execute_async_script(
            "const done = arguments[arguments.length - 1];"
            "axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']}})"
            ".then(r => done(r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help,"
            " nodes: v.nodes.slice(0, 5).map(n => n.target.join(' '))}))), e => done([{id: 'axe-error', impact: 'critical', help: String(e), nodes: []}]));")
        return [v for v in result if v["impact"] in impacts]
