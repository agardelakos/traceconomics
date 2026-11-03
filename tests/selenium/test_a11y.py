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
    _check(site, f"/{lang}/{path}", theme)
    problems = site.axe()
    assert not problems, _report(problems)


@pytest.mark.phone
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize("path", PATHS)
def test_phone(phone, path, lang, theme):
    _check(phone, f"/{lang}/{path}", theme)
    problems = phone.axe()
    assert not problems, _report(problems)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("menu", ["#settings-menu", "#topic-menu", "#country-menu"])
def test_desktop_menus_open(site, menu, theme):
    _check(site, "/en/gr/inflation-by-group/", theme)
    site.find(f'[popovertarget="{menu[1:]}"]').click()
    site.wait(lambda _: site.popover_open(site.find(menu)))
    problems = site.axe()
    assert not problems, _report(problems)


@pytest.mark.phone
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_phone_menu_open(phone, theme):
    _check(phone, "/en/gr/inflation-by-group/", theme)
    phone.find(".menu-button").click()
    phone.wait(lambda _: phone.popover_open(phone.find("#site-menu")))
    problems = phone.axe()
    assert not problems, _report(problems)
