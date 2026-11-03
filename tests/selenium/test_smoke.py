"""The main pages load, in both languages, with a title, a heading, the main landmark and no console
error. Small enough to run against a deployed copy too (`-m smoke --base-url ...`)."""

import pytest

from helpers import t

PAGES = [
    "", "about/", "countries/", "topics/", "glossary/", "data/", "data/gr/", "inflation-by-group/",
    "gr/", "gr/inflation-by-group/", "gr/inflation-by-group/method/", "gr/inflation-by-group/groups/",
    "gr/inflation-by-group/explore/", "gr/inflation-by-group/calculator/",
]


@pytest.mark.smoke
@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize("page", PAGES)
def test_page_loads(site, lang, page):
    site.open(f"/{lang}/{page}")
    assert site.js("return document.documentElement.lang") == lang
    assert t(lang, "site.name") in site.driver.title
    assert site.find("main#content").is_displayed()
    assert site.find("h1").text.strip()


@pytest.mark.smoke
def test_root_goes_to_english(site):
    site.open("/")
    site.wait(lambda _: site.path == "/en/", f"the root stayed at {site.driver.current_url}")
