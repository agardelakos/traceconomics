"""Terms with an explanation (glossary terms, method options), and the glossary's search.

With a mouse, pointing at a term opens its explanation and a click goes to its page. From the
keyboard and on touch screens, pressing the term opens the explanation (which holds the link);
Escape or a tap elsewhere closes it."""

import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

PAGE = "/en/gr/inflation-by-group/groups/"


def _term(site):
    button = site.visible(".term-wrap button.term")
    pop = site.find("#" + button.get_attribute("popovertarget"))
    link = pop.find_element("css selector", "a").get_attribute("href")
    return button, pop, link


def test_hover_opens_and_leaving_closes(site):
    site.open(PAGE)
    button, pop, _ = _term(site)
    ActionChains(site.driver).move_to_element(button).perform()
    site.wait(lambda _: site.popover_open(pop), "pointing at the term did not open it")
    ActionChains(site.driver).move_to_element(site.find("h1")).perform()
    site.wait(lambda _: not site.popover_open(pop), "moving away did not close it")


def test_pointer_can_move_into_the_explanation(site):
    site.open(PAGE)
    button, pop, _ = _term(site)
    ActionChains(site.driver).move_to_element(button).perform()
    site.wait(lambda _: site.popover_open(pop))
    ActionChains(site.driver).move_to_element(pop).perform()
    # Moving across stays within the close delay, so the explanation is still open once inside.
    site.wait(lambda _: site.popover_open(pop))
    assert site.js("return arguments[0].matches(':hover')", pop)


def test_mouse_click_follows_the_link(site):
    site.open(PAGE)
    button, _, link = _term(site)
    button.click()
    site.wait(lambda _: site.driver.current_url == link, "a click on a term did not go to its page")


@pytest.mark.parametrize("close", ["escape", "enter"])
def test_keyboard_opens_and_closes(site, close):
    site.open(PAGE)
    button, pop, _ = _term(site)
    site.js("arguments[0].focus()", button)
    button.send_keys(Keys.ENTER)
    site.wait(lambda _: site.popover_open(pop), "Enter did not open the explanation")
    assert site.path == PAGE, "Enter followed the link instead of opening the explanation"
    site.driver.switch_to.active_element.send_keys(Keys.ESCAPE if close == "escape" else Keys.ENTER)
    site.wait(lambda _: not site.popover_open(pop), f"{close} did not close the explanation")


@pytest.mark.phone
def test_touch_opens_and_tap_elsewhere_closes(phone):
    phone.open(PAGE)
    button, pop, link = _term(phone)
    phone.js("arguments[0].scrollIntoView({block: 'center'})", button)
    button.click()
    phone.wait(lambda _: phone.popover_open(pop), "a tap did not open the explanation")
    assert phone.path == PAGE, "a tap followed the link"
    assert pop.find_element("css selector", "a").is_displayed()
    phone.find("h1").click()
    phone.wait(lambda _: not phone.popover_open(pop), "a tap elsewhere did not close it")


def _shown(site):
    return [li.get_attribute("data-text") for li in site.all("#glossary-list li[data-text]") if li.is_displayed()]


def test_glossary_search_filters(site):
    site.open("/en/glossary/")
    every = _shown(site)
    box = site.find("#glossary-search")
    box.send_keys("quintile")
    site.wait(lambda _: 0 < len(_shown(site)) < len(every), "the search did not filter")
    assert all("quintile" in text for text in _shown(site))
    box.send_keys("zzzz")
    site.wait(lambda _: _shown(site) == [])
    assert not any(g.is_displayed() for g in site.all("#glossary-list > .glossary-group")), "an empty category stayed"
    box.clear()
    box.send_keys(" ")
    box.send_keys(Keys.BACKSPACE)
    site.wait(lambda _: len(_shown(site)) == len(every), "clearing the search did not bring every term back")


def test_glossary_search_ignores_accents(site):
    site.open("/el/glossary/")
    every = _shown(site)
    accented = next(text for text in every if "πληθωρισμός" in text)
    site.find("#glossary-search").send_keys("πληθωρισμος")
    site.wait(lambda _: accented in _shown(site) and len(_shown(site)) < len(every),
              "an unaccented search missed the accented term")
