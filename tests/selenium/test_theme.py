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
    """SEL-THEME-001: the control starts on the device setting

    Given a first visit
    When the English home page opens
    Then the theme control shows, with "device setting" picked
    And no theme is applied or stored
    """
    site.open("/en/")
    assert site.find(".settings[data-role=theme]").is_displayed(), "the theme control stayed hidden"
    assert _checked(site) == "system"
    assert _state(site) == [None, None]


@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize("value", ["light", "dark"])
def test_choice_applies_and_is_stored(site, lang, value):
    """SEL-THEME-002: a theme choice applies and is stored

    Given the About page, in English or Greek
    When a theme, light or dark, is picked in the settings menu
    Then the page takes that theme and it is stored
    And the control shows it picked
    """
    site.open(f"/{lang}/about/")
    _pick(site, value, lang)
    site.wait(lambda _: _state(site) == [value, value], f"theme {value} was not applied")
    assert _checked(site) == value


def test_choice_holds_from_page_to_page(site):
    """SEL-THEME-003: the choice holds from page to page

    Given the dark theme picked on the home page
    When the Glossary link in the header is followed
    Then the glossary is dark, with dark still stored
    And the control shows dark picked
    """
    site.open("/en/")
    _pick(site, "dark")
    site.wait(lambda _: _state(site) == ["dark", "dark"])
    site.find('nav#site-menu a[href="/en/glossary/"]').click()
    site.wait(lambda _: site.path == "/en/glossary/")
    assert _state(site) == ["dark", "dark"]
    assert _checked(site) == "dark"


def test_device_setting_clears_storage(site):
    """SEL-THEME-004: "device setting" clears the stored choice

    Given the light theme picked
    When "device setting" is picked
    Then no theme is applied or stored
    And nothing at all is stored
    """
    site.open("/en/")
    _pick(site, "light")
    site.wait(lambda _: _state(site) == ["light", "light"])
    _pick(site, "system")
    site.wait(lambda _: _state(site) == [None, None], "device setting left a stored theme")
    assert site.storage() == {}


def test_stored_choice_applies_before_drawing(site):
    """SEL-THEME-005: a stored choice applies before the page is drawn

    Given dark stored as the theme
    When the page loads again
    Then the page is dark as soon as it has loaded

    The head's small script reads the stored choice before the page is drawn: no flash.
    """
    # The head's small script reads the stored choice before the page is drawn: no flash.
    site.open("/en/")
    site.js("localStorage.setItem('theme', 'dark')")
    site.reload()
    assert site.js("return document.documentElement.getAttribute('data-theme')") == "dark"


def _device(site, scheme):
    site.driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": scheme}]})


def test_device_setting_follows_the_system(site):
    """SEL-THEME-006: the device setting follows the system

    Given the home page on the device setting, with a light background
    When the device switches to dark
    Then the background changes with the device
    """
    site.open("/en/")
    light = _background(site)
    _device(site, "dark")
    site.wait(lambda _: _background(site) != light, "the device's dark setting changed nothing")


def test_a_choice_overrides_the_device_setting(site):
    """SEL-THEME-009: a choice overrides the device setting

    Given the home page on the device setting, its light background noted, then the device switched to dark
    When light is picked
    And then dark is picked
    Then light brings back the light background, though the device is dark
    And dark brings back the device's dark background
    """
    site.open("/en/")
    light = _background(site)
    _device(site, "dark")
    site.wait(lambda _: _background(site) != light, "the device's dark setting changed nothing")
    dark = _background(site)
    _pick(site, "light")
    site.wait(lambda _: _background(site) == light, "a light choice did not override the device's dark setting")
    _pick(site, "dark")
    site.wait(lambda _: _background(site) == dark)


def test_unknown_stored_value_means_device_setting(site):
    """SEL-THEME-007: an unknown stored value means the device setting

    Given a theme stored that doesn't exist
    When the page loads again
    Then no theme is applied
    And the control shows "device setting" picked
    """
    site.open("/en/")
    site.js("localStorage.setItem('theme', 'purple')")
    site.reload()
    assert site.js("return document.documentElement.getAttribute('data-theme')") is None
    assert _checked(site) == "system"


@pytest.mark.phone
def test_phone_menu_copy_stays_in_step(phone):
    """SEL-THEME-008: the phone menu's copy stays in step

    Given the home page on a phone, with the menu open
    When dark is picked in the menu's theme control
    Then the page is dark and dark is stored
    And both the menu's and the header's controls show dark picked
    """
    phone.open("/en/")
    phone.visible(".menu-button").click()
    label = next(lb for lb in phone.all(".menu-settings label") if lb.text.strip() == t("en", "theme.dark"))
    label.click()
    phone.wait(lambda _: _state(phone) == ["dark", "dark"])
    assert _checked(phone, "theme-menu") == "dark"
    assert _checked(phone, "theme") == "dark", "the header's copy did not follow the menu's"
