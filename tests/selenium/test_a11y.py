"""Accessibility with axe-core (WCAG 2.0 to 2.2, A and AA): no serious or critical problem on the
main pages, in both languages, light and dark, on a desktop and a phone, and with the menus open.
Pages that draw with a script are checked once they have drawn."""

import pytest

PATHS = [
    "", "about/", "countries/", "topics/", "glossary/", "glossary/quintile/", "data/", "data/gr/",
    "inflation-by-group/", "gr/", "gr/inflation-by-group/", "gr/inflation-by-group/method/",
    "gr/inflation-by-group/method/weights-timing/", "gr/inflation-by-group/groups/",
    "gr/inflation-by-group/explore/", "gr/inflation-by-group/calculator/",
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
