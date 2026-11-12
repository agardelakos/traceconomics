"""What a reader types stays in the page. No request carries a typed income or amount of euros,
the page talks only to its own site, localStorage holds at most the theme, no cookie is set, and
the finder's links carry groups, never the income. Requests are read from Chrome's own log of
everything the page sent."""

from urllib.parse import unquote, urlsplit

import pytest

from selenium.webdriver.common.keys import Keys

GR = "/en/gr/inflation-by-group/"
INCOME = "23457"  # odd enough not to occur in any file name or number by chance
EUROS = ["611", "389"]


def _leaks(site, secrets):
    # The log must have seen the page's own data request, or an empty log would pass every check.
    assert any("/data/v1/" in r["url"] for r in site.requests()), "no request was recorded at all"
    out = []
    for r in site.requests():
        seen = unquote(r["url"]) + " " + unquote(r["body"])
        out += [f"{s} in {r['method']} {r['url']}" for s in secrets if s in seen]
    return out


def _foreign(site):
    base = urlsplit(site.base).netloc
    return [
        r["url"]
        for r in site.requests()
        if urlsplit(r["url"]).scheme in ("http", "https") and urlsplit(r["url"]).netloc != base
    ]


def _stored_and_cookies(site):
    keys = set(site.storage())
    cookies = site.driver.get_cookies()
    doc = site.js("return document.cookie")
    return keys, cookies, doc


def test_finder_keeps_the_income_in_the_page(site):
    """SEL-PRIV-001: the finder keeps the income in the page

    Given the group finder
    When an income is typed and renting is chosen
    And the link to compare the groups in Explore is followed
    Then no link the finder offers carries the income
    And neither Explore's address nor any request the pages sent carries it
    And the pages talked only to their own site
    And nothing but the theme is stored, and no cookie is set
    """
    site.open(GR + "groups/")
    site.visible("[data-find=form]")
    site.find("[data-find=income]").send_keys(INCOME)
    site.find('input[name="home"][value="renter"]').find_element("xpath", "./ancestor::label").click()
    site.visible("[data-find=income-row]")
    links = [a.get_attribute("href") for a in site.all("[data-find=starts] a, [data-find=compare]")]
    assert links and not [h for h in links if INCOME in h], "a link carries the income"
    site.find("[data-find=compare]").click()
    site.wait(lambda _: site.path.endswith("/explore/"))
    site.scripts_ran("#explore [data-role=chart]")
    assert INCOME not in site.driver.current_url
    assert not _leaks(site, [INCOME])
    assert not _foreign(site)
    keys, cookies, doc = _stored_and_cookies(site)
    assert keys <= {"theme"} and not cookies and doc == ""


def test_calculator_keeps_the_euros_in_the_page(site):
    """SEL-PRIV-002: the calculator keeps the euros in the page

    Given the calculator, switched to euros a month
    When two amounts are typed and totalled
    Then the address carries nothing but the starting group, and neither amount
    And no request the page sent carries either amount
    And the page talked only to its own site
    And nothing but the theme is stored, and no cookie is set
    """
    site.open(GR + "calculator/")
    site.visible("[data-role=result]")
    site.find("[data-mode=euros]").click()
    site.visible("[data-role=pane-euros]")
    for box, amount in zip(site.all("[data-role=euros] input")[:2], EUROS):
        box.send_keys(amount)
    site.wait(lambda _: "€1" in site.find("[data-role=euros-total]").text)
    assert not [k for k in site.query if k != "from"], "the address carries more than the starting group"
    assert all(e not in site.driver.current_url for e in EUROS)
    assert not _leaks(site, EUROS)
    assert not _foreign(site)
    keys, cookies, doc = _stored_and_cookies(site)
    assert keys <= {"theme"} and not cookies and doc == ""


def test_calculator_sliders_stay_in_the_page(site):
    """SEL-PRIV-003: the calculator's sliders stay in the page

    Given the calculator
    When the first slider moves
    Then the address doesn't carry its new value
    And the page sent nothing but GET requests
    And nothing is stored
    """
    site.open(GR + "calculator/")
    site.visible("[data-role=result]")
    slider = site.find("#div-01")
    before = slider.get_attribute("value")
    slider.send_keys(Keys.ARROW_RIGHT * 7)
    site.wait(lambda _: slider.get_attribute("value") != before)
    value = slider.get_attribute("value")
    assert value not in site.driver.current_url
    assert not [r for r in site.requests() if r["method"] != "GET"], "the page sent something"
    assert site.storage() == {}


def test_theme_is_the_only_thing_stored(site):
    """SEL-PRIV-004: the theme is the only thing stored

    Given the English home page
    When the dark theme is picked
    And the About page, Explore and the calculator are opened in turn, each left to load its data
    Then on each page the only thing stored is the theme, dark, and no cookie is set
    And no page talked to another site, each page's own requests checked apart so a failure names the page
    """
    site.open("/en/")
    site.find(".settings[data-role=theme] button").click()
    site.find('#settings-menu input[value="dark"]').find_element("xpath", "./ancestor::label").click()
    site.wait(lambda _: site.storage() == {"theme": "dark"})
    base = urlsplit(site.base).netloc
    # What each page shows once its own data requests are done, so they are in the log.
    pages = {
        "about/": "main h1",
        "gr/inflation-by-group/explore/": "#explore [data-role=chart] svg",
        "gr/inflation-by-group/calculator/": "[data-role=result]",
    }
    for page, ready in pages.items():
        before = len(site.requests())
        site.open(f"/en/{page}")
        site.visible(ready)
        mine = site.requests()[before:]
        foreign = [
            r["url"]
            for r in mine
            if urlsplit(r["url"]).scheme in ("http", "https") and urlsplit(r["url"]).netloc != base
        ]
        assert not foreign, f"/en/{page} talked to another site: {foreign}"
        assert site.storage() == {"theme": "dark"}, f"/en/{page} stored {site.storage()}"
        assert not site.driver.get_cookies(), f"/en/{page} set a cookie"


@pytest.mark.parametrize(
    "path, ready",
    [
        (GR, "main h1"),
        ("/en/data/gr/", "main h1"),
        ("/en/glossary/", "#glossary-list"),
    ],
    ids=["topic page", "data page", "glossary"],
)
def test_the_topic_data_and_glossary_pages_ask_nothing_of_other_sites(site, path, ready):
    """SEL-PRIV-005: the topic page, the data page and the glossary ask nothing of other sites

    Given the inflation-by-group page for Greece, the data page for Greece, or the glossary
    When it opens and finishes loading
    Then no request it sent goes to another site
    """
    site.open(path)
    site.visible(ready)
    # The log must have seen the page itself, or an empty log would pass.
    assert any(urlsplit(r["url"]).path == path for r in site.requests()), "the page's own request was not recorded"
    assert not _foreign(site), f"{path} talked to another site: {_foreign(site)}"
