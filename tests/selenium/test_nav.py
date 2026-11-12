"""The header: the quick lists of topics and countries, the phone menu, the language switch, the
skip link and the breadcrumbs."""

import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import pytest
from helpers import ROOT, t
from selenium.webdriver.common.keys import Keys

# The languages offered to readers, as the site's own list has them.
OFFERED = json.loads((ROOT / "site/src/i18n/languages.json").read_text(encoding="utf-8"))["offered"]
# The languages the site is built in: one interface file each (en.json, el.json).
BUILT = sorted(p.stem for p in (ROOT / "site/src/i18n").glob("??.json"))

TOPIC_PAGE = "/{lang}/gr/inflation-by-group/explore/"


def _arrow(site, lang, which):
    label = t(lang, "nav.quick", name=t(lang, f"nav.{which}"))
    return site.find(f'button.nav-arrow[aria-label="{label}"]')


@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize(
    "which,menu,current", [("topics", "#topic-menu", "inflation-by-group"), ("countries", "#country-menu", "gr")]
)
def test_quick_list_opens_ticks_current_and_closes_with_escape(site, lang, which, menu, current):
    """SEL-NAV-001: a quick list opens, ticks the current entry and closes with Escape

    Given Explore, in English or Greek
    When the arrow next to Topics or Countries is pressed
    And Escape is pressed
    Then the quick list opens
    And exactly one entry is marked current, the page's own topic or country, with a tick
    And the list closes
    """
    site.open(TOPIC_PAGE.format(lang=lang))
    arrow = _arrow(site, lang, which)
    arrow.click()
    pop = site.find(menu)
    site.wait(lambda _: site.popover_open(pop), f"{menu} did not open")
    ticked = site.all(f'{menu} a[aria-current="true"]')
    assert len(ticked) == 1
    name = t(lang, f"topic.{current}" if which == "topics" else f"country.{current}")
    assert ticked[0].text.strip() == name
    assert ticked[0].find_elements("css selector", "svg"), "the current entry has no tick"
    site.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
    site.wait(lambda _: not site.popover_open(pop), f"{menu} did not close on Escape")


def test_quick_list_entry_goes_to_its_page(site):
    """SEL-NAV-002: a quick list entry goes to its page

    Given the About page
    When the countries' quick list is opened and Greece is picked
    Then the browser goes to the Greece page
    """
    site.open("/en/about/")
    _arrow(site, "en", "countries").click()
    link = site.visible('#country-menu a[href$="/gr/"]')
    link.click()
    site.wait(lambda _: site.path == "/en/gr/")


def test_country_list_keeps_the_page_the_reader_is_on(site):
    """SEL-NAV-003: the country list keeps the page the reader is on

    Given the calculator for Greece
    When the countries' quick list is opened
    Then the current country's entry shows
    And it links to this same calculator page
    """
    site.open("/en/gr/inflation-by-group/calculator/")
    arrow = _arrow(site, "en", "countries")
    arrow.click()
    site.wait(lambda _: site.popover_open(site.find("#country-menu")), "the countries' quick list did not open")
    current = site.visible('#country-menu a[aria-current="true"]')
    assert current.get_attribute("href").endswith("/en/gr/inflation-by-group/calculator/")


def test_section_is_marked_current(site):
    """SEL-NAV-004: on a section's own page, its link alone is marked as the current page

    Given the glossary
    When its header's navigation is read
    Then the Glossary link alone is marked as the current page
    """
    site.open("/en/glossary/")
    current = site.all('nav#site-menu a[aria-current="page"]')
    assert [a.text for a in current] == [t("en", "nav.glossary")]


def test_a_page_inside_a_section_marks_the_section(site):
    """SEL-NAV-015: on a page inside a section, the section is marked current

    Given the topic page for Greece, which is inside Countries
    When its header's navigation is read
    Then the Countries link is marked as the current section ("true")
    """
    site.open("/en/gr/inflation-by-group/")
    countries = site.find('nav#site-menu a[href="/en/countries/"]')
    assert countries.get_attribute("aria-current") == "true"


def test_desktop_shows_the_navigation_as_a_row(site):
    """SEL-NAV-005: a desktop shows the navigation as a row

    Given a desktop
    When the home page opens
    Then the navigation and the theme control show
    And the phone's menu button doesn't
    """
    site.open("/en/")
    assert not site.find(".menu-button").is_displayed()
    assert site.find("nav#site-menu").is_displayed()
    assert site.find(".settings[data-role=theme] button").is_displayed()


@pytest.mark.phone
def test_phone_menu_opens_and_closes(phone):
    """SEL-NAV-006: the phone menu opens and closes

    Given the About page on a phone
    When the menu button is pressed
    And Escape is pressed
    Then the navigation is hidden at first
    And the menu opens, with links to Home and About and the theme control
    And the menu closes
    """
    phone.open("/en/about/")
    button = phone.visible(".menu-button")
    nav = phone.find("nav#site-menu")
    assert not nav.is_displayed()
    button.click()
    phone.wait(lambda _: phone.popover_open(nav) and nav.is_displayed(), "the phone menu did not open")
    links = [a.text for a in phone.all("nav#site-menu > ul > li > a") if a.is_displayed()]
    assert t("en", "nav.home") in links and t("en", "nav.about") in links
    assert phone.find(".menu-settings[data-role=theme]").is_displayed()
    phone.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
    phone.wait(lambda _: not phone.popover_open(nav), "the phone menu did not close")


@pytest.mark.phone
def test_phone_menu_link_navigates(phone):
    """SEL-NAV-007: a link in the phone menu goes to its page

    Given the home page on a phone, with the menu open
    When the Glossary link is picked
    Then the browser goes to the glossary
    """
    phone.open("/en/")
    phone.visible(".menu-button").click()
    phone.visible('nav#site-menu a[href="/en/glossary/"]').click()
    phone.wait(lambda _: phone.path == "/en/glossary/")


@pytest.mark.parametrize("path", ["/en/", "/en/about/", TOPIC_PAGE.format(lang="en")], ids=["home", "about", "explore"])
def test_language_switch_on_english_pages(site, path):
    """SEL-NAV-008: the language switch on an English page

    Given an English page: the home page, About or Explore
    When the language switch is read
    Then English is linked and marked current
    And each other offered language links to the same page in that language
    And a language not yet offered is shown but not linked
    """
    site.open(path)
    box = site.find(f'.lang-switch[role=group][aria-label="{t("en", "lang.switch")}"]')
    en = site.find('a[lang="en"]', box)
    assert en.get_attribute("aria-current") == "true"
    for lang in BUILT:
        if lang == "en":
            continue
        other = site.find(f'[lang="{lang}"]', box)
        if lang in OFFERED:
            assert other.tag_name == "a", f"{lang} is offered but not linked"
            assert urlsplit(other.get_attribute("href")).path == path.replace("/en/", f"/{lang}/", 1)
        else:
            assert other.tag_name == "span" and other.get_attribute("aria-disabled") == "true", (
                f"{lang} is linked though not offered"
            )


def test_language_switch_from_greek_page(site):
    """SEL-NAV-009: the language switch on a Greek page

    Given the Greek About page
    When English is picked in the language switch
    Then Greek was marked current in it
    And the browser goes to the English About page
    """
    site.open("/el/about/")
    box = site.find(".lang-switch")
    assert site.find('a[lang="el"]', box).get_attribute("aria-current") == "true"
    site.find('a[lang="en"]', box).click()
    site.wait(lambda _: site.path == "/en/about/")


def test_skip_link_moves_to_the_content(site):
    """SEL-NAV-010: the skip link moves to the content

    Given the About page
    When Tab is pressed once
    And Enter is pressed on what has focus
    Then the skip link has focus and shows
    And the address moves to the main content
    """
    site.open("/en/about/")
    site.find("body").send_keys(Keys.TAB)
    skip = site.driver.switch_to.active_element
    assert "skip-link" in skip.get_attribute("class")
    assert skip.is_displayed(), "the skip link stays invisible when focused"
    skip.send_keys(Keys.ENTER)
    site.wait(lambda _: site.driver.current_url.endswith("#content"))


@pytest.mark.parametrize(
    "path,trail",
    [
        ("/en/glossary/", ["nav.home", "nav.glossary"]),
        ("/en/data/gr/", ["nav.home", "nav.data", "country.gr"]),
    ],
)
def test_breadcrumbs(site, path, trail):
    """SEL-NAV-011: the breadcrumbs show the trail and lead home

    Given a page below the home page
    When its breadcrumbs are read
    And their first link is followed
    Then they show the expected trail, each step linked but the page itself
    And the browser goes to the home page
    """
    site.open(path)
    crumb = site.find(f'nav.breadcrumb[aria-label="{t("en", "breadcrumb")}"]')
    assert [p.strip() for p in crumb.text.split("/")] == [t("en", k) for k in trail]
    links = site.all("a", crumb)
    assert len(links) == len(trail) - 1, "the page itself should not be a link"
    links[0].click()
    site.wait(lambda _: site.path == "/en/")


def test_missing_page_is_404(base_url):
    """SEL-NAV-012: a missing page answers 404

    Given an address the site doesn't have
    When it is fetched
    Then it answers 404
    """
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(base_url + "/en/no-such-page/", timeout=30)
    assert e.value.code == 404


def test_opening_one_quick_list_closes_the_other(site):
    """SEL-NAV-013: opening one quick list closes the other

    Given the home page, with the Topics quick list open
    When the Countries quick list is opened
    Then the Countries list is shown
    And the Topics list is closed
    """
    site.open("/en/")
    topics, countries = site.find("#topic-menu"), site.find("#country-menu")
    _arrow(site, "en", "topics").click()
    site.wait(lambda _: site.popover_open(topics), "the Topics list did not open")
    _arrow(site, "en", "countries").click()
    site.wait(lambda _: site.popover_open(countries), "the Countries list did not open")
    assert not site.popover_open(topics), "the Topics list stayed open"


@pytest.mark.parametrize("locale", ["el-GR", "en-US", "de-DE"])
def test_root_sends_the_browser_to_its_language(site, locale):
    """SEL-NAV-014: the root address sends the visitor to the browser's language if offered, else English

    Given a browser set to Greek, US English or German
    When the site's root address is opened
    Then the visitor is sent to the home page in the browser's language if the site offers it, else in English
    """
    agent = site.driver.execute_script("return navigator.userAgent")
    site.driver.execute_cdp_cmd("Emulation.setUserAgentOverride", {"userAgent": agent, "acceptLanguage": locale})
    try:
        site.open("/")
        assert site.js("return navigator.languages[0]") == locale, "the browser's language was not set"
        wanted = locale.split("-")[0]
        expected = wanted if wanted in OFFERED else "en"
        site.wait(lambda _: site.path == f"/{expected}/", f"the root did not send a {locale} browser to /{expected}/")
    finally:
        site.driver.execute_cdp_cmd(
            "Emulation.setUserAgentOverride", {"userAgent": agent, "acceptLanguage": "en-GB,en"}
        )


@pytest.mark.phone
def test_topic_bar_rows_open_scrolled_to_their_current_item(phone):
    """SEL-NAV-016: on a phone, each row of the topic bar opens scrolled to its current item

    Given a phone-sized screen
    And Greece's page of the consistency topic, whose row of topics is wider than the screen with the current topic last
    When it is opened
    Then in every row of the bar wider than the screen, the current item is wholly inside the row's visible part
    """
    phone.open("/en/gr/official-figures-consistency/")
    wide = 0
    for row in phone.all(".topic-bar nav ul"):
        box = phone.driver.execute_script(
            "const r = arguments[0].getBoundingClientRect(); return {scroll: arguments[0].scrollWidth, client: arguments[0].clientWidth, left: r.left};",
            row,
        )
        if box["scroll"] <= box["client"]:
            continue
        wide += 1
        item = phone.driver.execute_script(
            "const r = arguments[0].getBoundingClientRect(); return {x: r.left, w: r.width};",
            row.find_element("css selector", "[aria-current]"),
        )
        assert box["left"] - 1 <= item["x"] and item["x"] + item["w"] <= box["left"] + box["client"] + 1
    assert wide > 0


def test_method_option_strip_lists_every_option(site):
    """SEL-NAV-017: on a method option's page, the bar's third row lists every option and marks the one being read

    Given the method page, which lists every option, and one option's page
    When the option's page is opened from the method page
    Then the bar's third row lists the options in the method page's order, by their titles
    And the option being read is plain text marked current; the others link to their pages
    And the Method tab is marked as the current section
    """
    site.open("/en/gr/inflation-by-group/method/")
    cards = site.all('nav[aria-labelledby="options-h"] a.card')
    titles = [c.find_element("css selector", ".title").text.strip().removesuffix(" →") for c in cards]
    hrefs = [c.get_attribute("href") for c in cards]
    cards[1].click()
    site.wait(lambda _: site.driver.current_url == hrefs[1], "the option's page did not open")
    assert [li.text.strip() for li in site.all("nav[data-strip] li")] == titles
    assert site.find('nav[data-strip] [aria-current="page"]').text.strip() == titles[1]
    links = {a.text.strip(): a.get_attribute("href") for a in site.all("nav[data-strip] a")}
    assert links == {title: href for i, (title, href) in enumerate(zip(titles, hrefs, strict=True)) if i != 1}
    tab = next(a for a in site.all(".topic-nav.sub a") if a.text.strip() == t("en", "nav.method"))
    assert tab.get_attribute("aria-current") == "true"


def test_topics_quick_list_names_every_live_topic(site):
    """SEL-NAV-018: the Topics quick list names every live topic and leads to its page

    Given Greece's page of the consistency topic
    When the arrow beside Topics in the header is pressed
    Then the list links to both live topics, inflation by household and the consistency of official figures, each to its page
    And the consistency topic is marked as the current one
    """
    site.open("/en/gr/official-figures-consistency/")
    _arrow(site, "en", "topics").click()
    pop = site.find("#topic-menu")
    site.wait(lambda _: site.popover_open(pop), "#topic-menu did not open")
    links = {a.text.strip(): a for a in site.all("#topic-menu a")}
    for slug in ("inflation-by-group", "official-figures-consistency"):
        assert links[t("en", f"topic.{slug}")].get_attribute("href").endswith(f"/en/{slug}/")
    assert links[t("en", "topic.official-figures-consistency")].get_attribute("aria-current") == "true"
