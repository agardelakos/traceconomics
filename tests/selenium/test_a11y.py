"""Accessibility with axe-core (WCAG 2.0 to 2.2, A and AA): no serious or critical problem on the
main pages, in both languages, light and dark, on a desktop and a phone, and with the menus open.
Pages that draw with a script are checked once they have drawn."""

import pytest

PATHS = [
    "", "about/", "countries/", "topics/", "glossary/", "glossary/quintile/", "data/", "data/gr/",
    "inflation-by-group/", "gr/", "gr/inflation-by-group/", "gr/inflation-by-group/method/",
    "gr/inflation-by-group/method/weights-timing/", "gr/inflation-by-group/groups/",
    "gr/inflation-by-group/explore/", "gr/inflation-by-group/calculator/",
    # The consistency topic: its page across countries, Greece's overview and Method, the check cards,
    # a check, a finding, the questions, a question with its chart and one with its source popovers.
    "official-figures-consistency/", "gr/official-figures-consistency/", "gr/official-figures-consistency/method/",
    "gr/official-figures-consistency/checks/", "gr/official-figures-consistency/checks/cpi-rates-own-index/",
    "gr/official-figures-consistency/checks/cpi-rates-own-index/june-2001/", "gr/official-figures-consistency/same-question/",
    "gr/official-figures-consistency/same-question/renters/", "gr/official-figures-consistency/same-question/rent-paid/",
]
DRAWN = {"gr/inflation-by-group/explore/": "#explore [data-role=chart]", "gr/inflation-by-group/calculator/": "#calculator [data-role=chart]"}


def _check(site, path, theme):
    site.open(path)
    site.js("localStorage.setItem('theme', arguments[0])", theme)
    site.reload()
    assert site.js("return document.documentElement.getAttribute('data-theme')") == theme
    for page, css in DRAWN.items():
        if path.endswith(page):
            site.scripts_ran(css)


def _report(problems):
    return "\n".join(f"{p['impact']}: {p['id']} ({p['help']}) at {', '.join(p['nodes'])}" for p in problems)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize("path", PATHS)
def test_desktop(site, path, lang, theme):
    """SEL-A11Y-001: no serious accessibility problem on a desktop

    Given one of the main pages, in English or Greek, with the light or dark theme chosen, on a desktop
    And a page that draws a chart has drawn it
    When axe checks it against WCAG 2.0 to 2.2, A and AA
    Then it finds no serious or critical problem
    """
    _check(site, f"/{lang}/{path}", theme)
    problems = site.axe()
    assert not problems, _report(problems)


@pytest.mark.phone
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize("path", PATHS)
def test_phone(phone, path, lang, theme):
    """SEL-A11Y-002: no serious accessibility problem on a phone

    Given one of the main pages, in English or Greek, with the light or dark theme chosen, on a phone
    And a page that draws a chart has drawn it
    When axe checks it against WCAG 2.0 to 2.2, A and AA
    Then it finds no serious or critical problem
    """
    _check(phone, f"/{lang}/{path}", theme)
    problems = phone.axe()
    assert not problems, _report(problems)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("menu", ["#settings-menu", "#topic-menu", "#country-menu"])
def test_desktop_menus_open(site, menu, theme):
    """SEL-A11Y-003: no serious accessibility problem with a header menu open

    Given the topic page in English, with the light or dark theme chosen, on a desktop
    When one of the header's menus (settings, topics or countries) is opened
    And axe checks the page against WCAG 2.0 to 2.2, A and AA
    Then it finds no serious or critical problem
    """
    _check(site, "/en/gr/inflation-by-group/", theme)
    site.find(f'[popovertarget="{menu[1:]}"]').click()
    site.wait(lambda _: site.popover_open(site.find(menu)))
    problems = site.axe()
    assert not problems, _report(problems)


@pytest.mark.phone
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_phone_menu_open(phone, theme):
    """SEL-A11Y-004: no serious accessibility problem with the phone menu open

    Given the topic page in English, with the light or dark theme chosen, on a phone
    When the menu is opened
    And axe checks the page against WCAG 2.0 to 2.2, A and AA
    Then it finds no serious or critical problem
    """
    _check(phone, "/en/gr/inflation-by-group/", theme)
    phone.find(".menu-button").click()
    phone.wait(lambda _: phone.popover_open(phone.find("#site-menu")))
    problems = phone.axe()
    assert not problems, _report(problems)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("lang", ["en", "el"])
def test_consistency_filter_and_definition_open(site, lang, theme):
    """SEL-A11Y-005: the consistency topic passes the accessibility check with a status filter applied and a source's definition open

    Given the consistency topic's Checks page and a question's page, in English or Greek, with the light or dark theme chosen, on a desktop
    When each status button on the Checks page is pressed in turn
    And on the rent-paid question, a source's definition is opened
    Then axe finds no serious or critical problem in each state
    """
    from selenium.webdriver.common.keys import Keys
    _check(site, f"/{lang}/gr/official-figures-consistency/checks/", theme)
    for button in site.all('[data-m5="filter"] button[data-filter]:not([data-filter="all"])'):
        button.click()
        site.wait(lambda _: button.get_attribute("aria-pressed") == "true", "the button was not pressed")
        problems = site.axe()
        assert not problems, _report(problems)
    site.open(f"/{lang}/gr/official-figures-consistency/same-question/rent-paid/")
    term = site.find('[data-m5="question"] th[data-m5-source] button.term')
    term.send_keys(Keys.ENTER)     # opens the definition on every device (a mouse click follows the link)
    pop = site.find('[data-m5="question"] th[data-m5-source] .term-popover')
    site.wait(lambda _: pop.is_displayed(), "the definition did not open")
    problems = site.axe()
    assert not problems, _report(problems)
