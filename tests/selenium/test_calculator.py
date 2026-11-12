"""The calculator: loading, then the result; untouched, a starting group's result is its published
rate; the starting groups and `?from=`; sliders (with the rescaled notice) and reset; spending in
euros (shares, the total, a wrong amount); the chart. Expected rates from the setting's published
series, which the calculator must reproduce exactly when nothing is changed."""

import pytest
from helpers import data, default_slug, latest, month, months, num, t
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.select import Select

PAGE = "/{lang}/gr/inflation-by-group/calculator/"
PRESETS = [
    "all/all",
    "B/Q1",
    "B/Q2",
    "B/Q3",
    "B/Q4",
    "B/Q5",
    "tenure/renter",
    "tenure/owner",
    "tenure/rent_free",
    "pensioners/pensioners",
    "pensioners/other",
    "hhtype/A1",
    "hhtype/A1_DCH",
    "hhtype/A2",
    "hhtype/A2_DCH",
    "hhtype/A_GE3",
    "hhtype/A_GE3_DCH",
]


def _rate(preset):
    series = data(f"series/{default_slug()}.json")
    i, v = latest(series["groups"][preset]["rch_a"])
    return months(series["start"], series["end"])[i], v


def _name(lang, preset):
    return t(lang, f"group.{preset[2:] if preset.startswith('B/') else preset}")


def _ready(site):
    site.visible("#calculator [data-role=result]")
    site.hidden("#calculator [data-role=loading]")
    site.wait(lambda _: site.find("#calculator [data-role=yours]").text != "")


@pytest.mark.parametrize("lang", ["en", "el"])
def test_default_result_is_the_published_rate(site, lang):
    """SEL-CALC-001: untouched, the result is the published rate

    Given the calculator, opened with nothing changed
    When the result is drawn
    Then your rate and the poorest fifth's rate are its published latest annual rate, for its month
    And the all-households rate is shown
    And it says your basket is the group's, with no Reset
    """
    site.open(PAGE.format(lang=lang))
    _ready(site)
    assert not site.find("#calculator [data-role=noscript]").is_displayed()
    period, rate = _rate("B/Q1")
    site.text("#calculator [data-role=yours]", f"{num(lang, rate)}%")
    site.text("#calculator [data-role=yours-label]", t(lang, "calc.yours", month=month(lang, period)))
    site.text("#calculator [data-role=same]", t(lang, "calc.same", preset=_name(lang, "B/Q1")))
    site.text("#calculator [data-role=preset-rate]", f"{num(lang, rate)}%")
    site.text("#calculator [data-role=all-rate]", f"{num(lang, _rate('all/all')[1])}%")
    assert not site.find("#calculator [data-role=reset]").is_displayed()
    assert "edited" not in site.find("#calculator [data-role=result]").get_attribute("class")


@pytest.mark.parametrize("preset", PRESETS)
def test_every_starting_group_gives_its_published_rate(site, preset):
    """SEL-CALC-002: every starting group gives its published rate

    Given the calculator in English
    When a starting group is picked
    Then the result is that group's published latest rate, under its name
    And the address carries the group
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    Select(site.find("#calculator select[data-role=preset]")).select_by_value(preset)
    if preset != "B/Q1":  # picking the one already shown changes nothing
        site.url_has(**{"from": preset})
    site.text("#calculator [data-role=yours]", f"{num('en', _rate(preset)[1])}%")
    site.text("#calculator [data-role=preset-name]", _name("en", preset))


def test_from_in_the_address_picks_the_starting_group(site):
    """SEL-CALC-003: the address picks the starting group

    Given an address with `?from=pensioners/pensioners`
    When the calculator opens
    Then pensioner households are the starting group, with their published rate
    """
    site.open(PAGE.format(lang="en") + "?from=pensioners/pensioners")
    _ready(site)
    assert site.js("return document.querySelector('[data-role=preset]').value") == "pensioners/pensioners"
    site.text("#calculator [data-role=yours]", f"{num('en', _rate('pensioners/pensioners')[1])}%")


def test_unknown_from_is_ignored(site):
    """SEL-CALC-004: an unknown group in the address is ignored

    Given an address with `?from=nobody`
    When the calculator opens
    Then the starting group is the default, the poorest fifth
    """
    site.open(PAGE.format(lang="en") + "?from=nobody")
    _ready(site)
    assert site.js("return document.querySelector('[data-role=preset]').value") == "B/Q1"


def test_slider_changes_the_result_and_reset_restores_it(site):
    """SEL-CALC-005: a slider changes the result; Reset restores it

    Given the calculator at the poorest fifth's basket
    When the first category goes up 5 points
    And Reset is pressed
    Then the other categories are rescaled so the shares still add up to 100%, and a notice says so
    And the difference from the group is stated
    And Reset brings back the group's rate and every slider
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    site.wait(lambda _: len(site.all("#calculator [data-role=sliders] input[type=range]")) > 1, "no sliders were built")
    sliders = site.all("#calculator [data-role=sliders] input[type=range]")
    before = [s.get_attribute("value") for s in sliders]
    period, rate = _rate("B/Q1")
    first = sliders[0]
    first.send_keys(Keys.ARROW_RIGHT * 50)  # +5 points of spending
    site.visible("#calculator [data-role=rescaled]")
    site.text("#calculator [data-role=rescaled]", t("en", "calc.rescaled"))
    site.wait(lambda _: "edited" in site.find("#calculator [data-role=result]").get_attribute("class"))
    assert float(first.get_attribute("value")) == pytest.approx(float(before[0]) + 5, abs=0.05)
    others = [float(s.get_attribute("value")) for s in sliders[1:]]
    # The page keeps the exact shares (they add up to 100) and shows each slider rounded to 0.1, so
    # each shown value is off by at most 0.05 and their sum by at most 0.05 per slider: with 13
    # categories that is 0.65, more than a fixed 0.2 allows on some baskets (99.8 on real data).
    rounding = 0.05 * len(sliders) + 1e-9
    assert sum(others) + float(first.get_attribute("value")) == pytest.approx(100, abs=rounding), (
        "the shares no longer add up to 100%"
    )
    assert others != [float(v) for v in before[1:]], "the other categories were not rescaled"
    diff = site.visible("#calculator [data-role=diff]").text
    assert _name("en", "B/Q1") in diff
    site.hidden("#calculator [data-role=same]")
    reset = site.visible("#calculator [data-role=reset]")
    assert reset.text == t("en", "calc.reset", preset=_name("en", "B/Q1"))
    reset.click()
    site.text("#calculator [data-role=yours]", f"{num('en', rate)}%")
    site.hidden("#calculator [data-role=rescaled]")
    site.hidden("#calculator [data-role=reset]")
    assert [s.get_attribute("value") for s in site.all("#calculator [data-role=sliders] input[type=range]")] == before


def test_slider_notes_say_what_moved(site):
    """SEL-CALC-006: each slider says whether it moved

    Given the calculator at a starting group's basket, every slider saying it is the group's
    When one slider moves
    Then that slider says you changed it
    And at least one other says it was adjusted to keep 100%
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    rows = site.wait(lambda _: site.all("#calculator .slider-row") or False)
    assert all(r.find_element("css selector", "span.small").text == t("en", "calc.as_preset") for r in rows)
    rows[0].find_element("css selector", "input").send_keys(Keys.ARROW_RIGHT * 30)
    site.wait(lambda _: rows[0].find_element("css selector", "span.small").text.endswith("you changed this"))
    assert any(r.find_element("css selector", "span.small").text.endswith("adjusted to keep 100%") for r in rows[1:])


def test_a_new_starting_group_resets_the_sliders(site):
    """SEL-CALC-007: a new starting group resets the sliders

    Given a slider moved away from the group's basket
    When renters are picked as the starting group
    Then the result is the renters' published rate
    And Reset is gone: nothing is changed any more
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    site.wait(lambda _: site.all("#div-01"))
    site.find("#div-01").send_keys(Keys.ARROW_RIGHT * 20)
    site.visible("#calculator [data-role=reset]")
    Select(site.find("#calculator select[data-role=preset]")).select_by_value("tenure/renter")
    site.text("#calculator [data-role=yours]", f"{num('en', _rate('tenure/renter')[1])}%")
    site.hidden("#calculator [data-role=reset]")


def test_spending_in_euros(site):
    """SEL-CALC-008: spending entered in euros

    Given the calculator switched to euros a month
    When three categories get 100, 200 and 100 euros
    And it switches back to shares
    Then the total and each category's share follow from the amounts
    And the result is marked as changed
    And the sliders start from the euros' shares
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    site.find("#calculator [data-mode=euros]").click()
    site.visible("#calculator [data-role=pane-euros]")
    site.hidden("#calculator [data-role=pane-shares]")
    assert site.find("#calculator [data-mode=euros]").get_attribute("aria-pressed") == "true"
    assert site.find("#calculator [data-role=euros-empty]").is_displayed()
    boxes = site.all("#calculator [data-role=euros] input")
    first, second = boxes[0].get_attribute("id"), boxes[3].get_attribute("id")
    boxes[0].send_keys("100")
    boxes[3].send_keys("200")
    boxes[5].send_keys("100")
    site.text("#calculator [data-role=euros-total]", t("en", "calc.euros.total", amount="€400"))
    site.text(f"#{first}-share", t("en", "calc.euros.share", share=f"{num('en', 25)}%"))
    site.text(f"#{second}-share", t("en", "calc.euros.share", share=f"{num('en', 50)}%"))
    site.hidden("#calculator [data-role=euros-empty]")
    site.wait(lambda _: "edited" in site.find("#calculator [data-role=result]").get_attribute("class"))
    # Back to shares: the sliders start from what the euros gave.
    site.find("#calculator [data-mode=shares]").click()
    site.visible("#calculator [data-role=pane-shares]")
    assert float(site.find("#" + first.replace("eur-", "div-")).get_attribute("value")) == pytest.approx(25)
    assert float(site.find("#" + second.replace("eur-", "div-")).get_attribute("value")) == pytest.approx(50)


def test_wrong_amount_is_marked_and_ignored(site):
    """SEL-CALC-009: a wrong amount is marked and ignored

    Given the calculator in euros
    When an amount that isn't a number is typed, then a valid one
    And the amounts are cleared
    Then the wrong amount is marked invalid and counts as nothing
    And the valid one is accepted and totalled
    And clearing empties the amounts
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    site.find("#calculator [data-mode=euros]").click()
    box = site.visible("#calculator [data-role=euros] input")
    box.send_keys("12,34,5")
    site.attr(f"#{box.get_attribute('id')}", "aria-invalid", "")
    site.text(f"#{box.get_attribute('id')}-share", t("en", "calc.euros.invalid"))
    assert site.find("#calculator [data-role=euros-empty]").is_displayed()
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys("1.250,50")
    site.attr(f"#{box.get_attribute('id')}", "aria-invalid", None)
    site.text("#calculator [data-role=euros-total]", t("en", "calc.euros.total", amount="€1 250.50"))
    reset = site.visible("#calculator [data-role=reset]")
    assert reset.text == t("en", "calc.euros.clear")
    reset.click()
    site.wait(lambda _: box.get_attribute("value") == "")
    site.visible("#calculator [data-role=euros-empty]")


def test_chart_shows_the_starting_group_then_yours(site):
    """SEL-CALC-010: the chart shows the starting group, then yours

    Given the calculator drawn
    When a slider moves
    Then the chart's label names the starting group alone at first
    And then the group and your basket
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    site.scripts_ran("#calculator [data-role=chart]")
    site.attr("#calculator [data-role=chart]", "aria-label", f"{t('en', 'calc.over_time')}: {_name('en', 'B/Q1')}")
    site.find("#div-01").send_keys(Keys.ARROW_RIGHT * 20)
    site.attr(
        "#calculator [data-role=chart]",
        "aria-label",
        f"{t('en', 'calc.over_time')}: {_name('en', 'B/Q1')}, {t('en', 'calc.title')}",
    )


@pytest.mark.console_errors
def test_data_that_fails_to_load_says_so(site):
    """SEL-CALC-011: data that fails to load says so

    Given the calculator's data file blocked
    When the calculator opens
    Then it says the data couldn't be loaded, and shows no result
    """
    site.driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": ["*calculator.json*"]})
    site.open(PAGE.format(lang="en"))
    site.text("#calculator [data-role=loading]", t("en", "chart.failed"))
    assert not site.find("#calculator [data-role=result]").is_displayed()
