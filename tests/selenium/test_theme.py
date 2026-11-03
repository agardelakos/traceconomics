"""The theme setting: device setting, light or dark; kept from page to page in localStorage (one
key, `theme`), removed again by "device setting"; both copies of the control (header and phone menu)
stay in step; the stored choice applies before the page is drawn."""

import pytest

from helpers import t


def _pick(site, value, lang="en"):
    """Opens the settings menu and picks a theme by its visible label, as a reader would."""
    menu = site.find("#settings-menu")
    if not site.popover_open(menu):
        site.find(".settings[data-role=theme] button").click()
    site.wait(lambda _: site.popover_open(menu), "the settings menu did not open")
    label = next(lb for lb in site.all("#settings-menu label") if lb.text.strip() == t(lang, f"theme.{value}"))
    label.click()


def _state(site):
    return site.js("return [document.documentElement.getAttribute('data-theme'), localStorage.getItem('theme')]")


def _checked(site, name="theme"):
    return site.js(f"return document.querySelector('input[name={name}]:checked')?.value ?? null")


def _background(site):
    return site.js("return getComputedStyle(document.body).backgroundColor")


def test_controls_start_on_device_setting(site):
    site.open("/en/")
    assert site.find(".settings[data-role=theme]").is_displayed(), "the theme control stayed hidden"
    assert _checked(site) == "system"
    assert _state(site) == [None, None]


@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize("value", ["light", "dark"])
def test_choice_applies_and_is_stored(site, lang, value):
    site.open(f"/{lang}/about/")
    _pick(site, value, lang)
    site.wait(lambda _: _state(site) == [value, value], f"theme {value} was not applied")
    assert _checked(site) == value


def test_choice_holds_from_page_to_page(site):
    site.open("/en/")
    _pick(site, "dark")
    site.wait(lambda _: _state(site) == ["dark", "dark"])
    site.find('nav#site-menu a[href="/en/glossary/"]').click()
    site.wait(lambda _: site.path == "/en/glossary/")
    assert _state(site) == ["dark", "dark"]
    assert _checked(site) == "dark"


def test_device_setting_clears_storage(site):
    site.open("/en/")
    _pick(site, "light")
    site.wait(lambda _: _state(site) == ["light", "light"])
    _pick(site, "system")
    site.wait(lambda _: _state(site) == [None, None], "device setting left a stored theme")
    assert site.storage() == {}


def test_stored_choice_applies_before_drawing(site):
    # The head's small script reads the stored choice before the page is drawn: no flash.
    site.open("/en/")
    site.js("localStorage.setItem('theme', 'dark')")
    site.reload()
    assert site.js("return document.documentElement.getAttribute('data-theme')") == "dark"


def test_device_setting_follows_the_system_and_choice_overrides_it(site):
    site.open("/en/")
    light = _background(site)
    site.driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": "dark"}]})
    site.wait(lambda _: _background(site) != light, "the device's dark setting changed nothing")
    dark = _background(site)
    _pick(site, "light")
    site.wait(lambda _: _background(site) == light, "a light choice did not override the device's dark setting")
    _pick(site, "dark")
    site.wait(lambda _: _background(site) == dark)


def test_unknown_stored_value_means_device_setting(site):
    site.open("/en/")
    site.js("localStorage.setItem('theme', 'purple')")
    site.reload()
    assert site.js("return document.documentElement.getAttribute('data-theme')") is None
    assert _checked(site) == "system"


@pytest.mark.phone
def test_phone_menu_copy_stays_in_step(phone):
    phone.open("/en/")
    phone.visible(".menu-button").click()
    label = next(lb for lb in phone.all(".menu-settings label") if lb.text.strip() == t("en", "theme.dark"))
    label.click()
    phone.wait(lambda _: _state(phone) == ["dark", "dark"])
    assert _checked(phone, "theme-menu") == "dark"
    assert _checked(phone, "theme") == "dark", "the header's copy did not follow the menu's"
