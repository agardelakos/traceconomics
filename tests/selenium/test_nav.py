"""The header: the quick lists of topics and countries, the phone menu, the language switch, the
skip link and the breadcrumbs."""

import urllib.error
import urllib.request

import pytest
from selenium.webdriver.common.keys import Keys

from helpers import t

TOPIC_PAGE = "/{lang}/gr/inflation-by-group/explore/"


def _arrow(site, lang, which):
    label = t(lang, "nav.quick", name=t(lang, f"nav.{which}"))
    return site.find(f'button.nav-arrow[aria-label="{label}"]')


@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize("which,menu,current", [("topics", "#topic-menu", "inflation-by-group"), ("countries", "#country-menu", "gr")])
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
    """SEL-NAV-004: the current section is marked in the header

    Given the glossary
    When its header's navigation is read
    And the topic page for Greece is opened
    Then on the glossary the Glossary link alone is marked as the current page
    And on the topic page the Countries link is marked current
    """
    site.open("/en/glossary/")
    current = site.all('nav#site-menu a[aria-current="page"]')
    assert [a.text for a in current] == [t("en", "nav.glossary")]
    site.open("/en/gr/inflation-by-group/")
    countries = site.find(f'nav#site-menu a[href="/en/countries/"]')
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
    And Greek is shown but not linked, as it isn't offered
    """
    site.open(path)
    box = site.find(f'.lang-switch[role=group][aria-label="{t("en", "lang.switch")}"]')
    en = site.find('a[lang="en"]', box)
    assert en.get_attribute("aria-current") == "true"
    el = site.find('[lang="el"]', box)
    assert el.tag_name == "span" and el.get_attribute("aria-disabled") == "true", "Greek is linked though not offered"


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


@pytest.mark.parametrize("path,trail", [
    ("/en/glossary/", ["nav.home", "nav.glossary"]),
    ("/en/data/gr/", ["nav.home", "nav.data", "country.gr"]),
])
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
