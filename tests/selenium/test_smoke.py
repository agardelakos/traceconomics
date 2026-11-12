"""The main pages load, in both languages, with a title, a heading, the main landmark and no console
error. Small enough to run against a deployed copy too (`-m smoke --base-url ...`)."""

import pytest
from helpers import t

PAGES = [
    "",
    "about/",
    "countries/",
    "topics/",
    "glossary/",
    "data/",
    "data/gr/",
    "inflation-by-group/",
    "gr/",
    "gr/inflation-by-group/",
    "gr/inflation-by-group/method/",
    "gr/inflation-by-group/groups/",
    "gr/inflation-by-group/explore/",
    "gr/inflation-by-group/calculator/",
    "official-figures-consistency/",
    "gr/official-figures-consistency/",
    "gr/official-figures-consistency/checks/",
    "gr/official-figures-consistency/checks/cpi-rates-own-index/",
    "gr/official-figures-consistency/checks/cpi-rates-own-index/june-2001/",
    "gr/official-figures-consistency/same-question/",
    "gr/official-figures-consistency/method/",
]


@pytest.mark.smoke
@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize("page", PAGES)
def test_page_loads(site, lang, page):
    """SEL-SMOKE-001: each main page loads

    Given one of the main pages, in English or Greek
    When it opens
    Then the page is in that language
    And its title carries the site's name
    And it shows the main content and a heading with text
    And the browser's console holds no error
    """
    site.open(f"/{lang}/{page}")
    assert site.js("return document.documentElement.lang") == lang
    assert t(lang, "site.name") in site.driver.title
    assert site.find("main#content").is_displayed()
    assert site.find("h1").text.strip()


@pytest.mark.smoke
def test_root_goes_to_english(site):
    """SEL-SMOKE-002: the root goes to English

    Given the site's root address
    When it opens
    Then the visitor lands on the English home page
    """
    site.open("/")
    site.wait(lambda _: site.path == "/en/", f"the root stayed at {site.driver.current_url}")
