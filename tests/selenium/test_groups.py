"""The Groups page: the group finder (household, income, home, pension -> the reader's groups, with
links to the calculator and Explore) and the income panel (each fifth's income range for a
household, in euros or purchasing power standards). Expected values from the published cut-offs."""

import pytest
from selenium.webdriver.common.keys import Keys

from helpers import cutoffs, data, equivalent_size, eur, household_type, js_round, num, pct, place_income, pps, t

PAGE = "/{lang}/gr/inflation-by-group/groups/"


def _set_number(site, css, value):
    box = site.find(css)
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys(str(value))


def _choose(site, name, value):
    site.find(f'input[name="{name}"][value="{value}"]').find_element("xpath", "./ancestor::label").click()


def _type_income(site, text):
    box = site.find("[data-find=income]")
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys(text)


# --- the finder ---------------------------------------------------------------------------------

def test_finder_shows_once_scripts_run(site):
    """SEL-GRP-001: the finder shows once scripts run

    Given the Groups page in English
    When it has loaded
    Then the finder's form shows and its no-script line is hidden
    And it asks for the income
    And the only group found is the household type of the form as it starts, a single adult, with one calculator link for it
    """
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    site.hidden("[data-find=noscript]")
    assert site.find("[data-find=empty]").is_displayed()
    # Before anything is entered, the only group is the household type of the form as it starts.
    site.text("[data-find=type-value]", t("en", "group.hhtype/A1"))
    assert [a.get_attribute("href").split("from=")[1] for a in site.all("[data-find=starts] a")] == ["hhtype%2FA1"]


@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize("older,children,typed,amount,per", [
    (1, 0, "9000", 9000, "year"),
    (2, 1, "1500", 1500, "month"),
    (2, 2, "45000", 45000, "year"),
    (3, 0, "2.000", 2000, "month"),
])
def test_finder_places_the_income(site, lang, older, children, typed, amount, per):
    """SEL-GRP-002: the finder places the income in its fifth

    Given the group finder
    When a household is entered (people aged 14 or over, children)
    And an income is typed, for a year or a month
    Then the household's size on the equivalence scale is shown
    And the income's fifth, from the published limits, is named
    And a warning about a nearby limit shows exactly when the income is within 5% of one
    And the calculator links start from that fifth and from the household's type
    """
    site.open(PAGE.format(lang=lang))
    site.visible("[data-find=form]")
    _set_number(site, "[data-find=older]", older)
    _set_number(site, "[data-find=children]", children)
    size = equivalent_size(older, children)
    site.text("[data-find=size]", t(lang, "income.size", size=num(lang, size)))
    _choose(site, "per", per)
    _type_income(site, typed)
    fifth, neighbour = place_income(cutoffs()["top_cutoffs"], size, amount * (12 if per == "month" else 1))
    site.text("[data-find=income-value]", t(lang, f"group.{fifth}"))
    assert site.find("[data-find=near]").is_displayed() == (neighbour is not None)
    starts = [a.get_attribute("href") for a in site.all("[data-find=starts] a")]
    kind = household_type(older, children, 0)
    assert len(starts) == 2 and starts[0].endswith(f"/calculator/?from=B%2F{fifth}")
    assert starts[1].endswith(f"/calculator/?from=hhtype%2F{kind}")


def test_finder_warns_near_a_limit(site):
    """SEL-GRP-003: the finder warns near a limit

    Given the group finder, for a single adult
    When a yearly income 2% under the limit between the second and third fifths is typed
    Then the income is placed in the second fifth
    And it warns that the income is near the third fifth
    """
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    q2 = cutoffs()["top_cutoffs"]["Q2"]
    _type_income(site, str(round(q2 * 0.98)))      # 2% under the line between the 2nd and 3rd fifths
    site.text("[data-find=income-value]", t("en", "group.Q2"))
    site.text("[data-find=near]", t("en", "find.near", group=t("en", "group.in.Q3")))


def test_finder_home_and_pension_and_links(site):
    """SEL-GRP-004: home and pension join the groups and the links

    Given the group finder, for a single adult with a yearly income
    When renting is chosen, and a pension as the main income
    And the link to compare the groups in Explore is followed
    Then the finder names renters and pensioner households
    And it offers calculator links for the income's fifth, the household type, renters and pensioners, in that order
    And the comparison link carries the same four groups
    And Explore opens with those four groups in its address
    """
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    _type_income(site, "12000")
    _choose(site, "home", "renter")
    _choose(site, "pension", "yes")
    site.text("[data-find=home-value]", t("en", "group.tenure/renter"))
    site.text("[data-find=pension-value]", t("en", "group.pensioners/pensioners"))
    fifth, _ = place_income(cutoffs()["top_cutoffs"], 1.0, 12000)
    starts = [a.get_attribute("href").split("?from=")[1] for a in site.all("[data-find=starts] a")]
    assert starts == [f"B%2F{fifth}", "hhtype%2FA1", "tenure%2Frenter", "pensioners%2Fpensioners"]
    compare = site.find("[data-find=compare]")
    assert compare.get_attribute("href").endswith(
        f"/explore/?groups={fifth}%2Chhtype%2FA1%2Ctenure%2Frenter%2Cpensioners%2Fpensioners")
    compare.click()
    site.wait(lambda _: site.path == "/en/gr/inflation-by-group/explore/")
    assert site.query["groups"].split(",") == [fifth, "hhtype/A1", "tenure/renter", "pensioners/pensioners"]


def test_finder_start_link_opens_the_calculator_on_that_group(site):
    """SEL-GRP-005: a start link opens the calculator on its group

    Given the group finder
    When owning the home is chosen
    And the calculator link for owners is followed
    Then the calculator opens with owners as its starting group
    """
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    _choose(site, "home", "owner")
    owner = [a for a in site.all("[data-find=starts] a") if a.get_attribute("href").endswith("from=tenure%2Fowner")]
    owner[0].click()
    site.wait(lambda _: site.path.endswith("/calculator/"))
    site.wait(lambda _: site.js("return document.querySelector('[data-role=preset]').value") == "tenure/owner")


@pytest.mark.parametrize("typed", ["abc", "1,50,0", "-5", "0"])
def test_finder_ignores_what_is_not_an_income(site, typed):
    """SEL-GRP-006: the finder ignores what is not an income

    Given the group finder
    When something that isn't a positive income is typed
    Then it still asks for the income
    And no income group is shown
    """
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    _type_income(site, typed)
    site.visible("[data-find=empty]")
    assert not site.find("[data-find=income-row]").is_displayed()


def test_finder_keeps_out_of_range_counts_in_bounds(site):
    """SEL-GRP-007: the finder keeps a count out of range in bounds

    Given the group finder
    When far more people than allowed are entered as aged 14 or over
    Then the household's size is that of the most the form allows, 12
    """
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    _set_number(site, "[data-find=older]", 40)      # max 12
    site.text("[data-find=size]", t("en", "income.size", size=num("en", equivalent_size(12, 0))))


# --- the income panel ---------------------------------------------------------------------------

def _expected(lang, size, unit, source="ours"):
    cuts = cutoffs(source)["top_cutoffs" if unit == "eur" else "top_cutoffs_pps"]
    amount = eur if unit == "eur" else pps
    tops = [cuts[q] * size for q in ("Q1", "Q2", "Q3", "Q4")]
    rows = []
    for i in range(5):
        lo = None if i == 0 else js_round(tops[i - 1])
        hi = None if i == 4 else js_round(tops[i])
        row = {}
        for per, d in (("year", 1), ("month", 12)):
            if lo is None:
                row[per] = t(lang, f"income.{per}.upto", amount=amount(hi / d))
            elif hi is None:
                row[per] = t(lang, f"income.{per}.over", amount=amount(lo / d))
            else:
                row[per] = t(lang, f"income.{per}.between", **{"from": amount(lo / d), "to": amount(hi / d)})
        rows.append(row)
    return rows


def _same(site, expected):
    """Waits until the table shows `expected`; on a timeout the message names each wrong cell."""
    seen = []

    def check(_):
        seen[:] = _cells(site)
        return seen == expected
    try:
        site.wait(check)
    except Exception:
        wrong = [f"Q{i + 1} {per}: {seen[i][per]!r}, expected {expected[i][per]!r}"
                 for i in range(5) for per in ("year", "month") if seen and seen[i][per] != expected[i][per]]
        raise AssertionError("\n".join(wrong) or "no table") from None


def _cells(site):
    # textContent, not .text: WebDriver's text turns the no-break space before "PPS" into a plain one.
    return [{"year": site.find(f'td[data-income-year="Q{i}"]').get_property("textContent"),
             "month": site.find(f'td[data-income-month="Q{i}"]').get_property("textContent")}
            for i in range(1, 6)]


@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize("household,older,children", [
    ("one", 1, 0), ("two", 2, 0), ("two_child", 2, 1), ("two_children", 2, 2), ("one_child", 1, 1), ("three", 3, 0),
])
def test_income_panel_household_types(site, lang, household, older, children):
    """SEL-GRP-008: the income panel for each listed household

    Given the Groups page, in English or Greek
    When one of the listed households is chosen in the income panel
    Then its size on the equivalence scale is shown
    And each fifth's yearly and monthly income range, in euros, follows from our published limits for that size
    """
    site.open(PAGE.format(lang=lang))
    _choose(site, "household", household)
    size = equivalent_size(older, children)
    site.text("[data-income-role=size]", t(lang, "income.size", size=num(lang, size)))
    _same(site, _expected(lang, size, "eur"))


def test_income_panel_other_size_and_pps(site):
    """SEL-GRP-009: the income panel for another household, in euros and PPS

    Given the income panel, its other-household fields hidden
    When another household is chosen, and four people aged 14 or over and three children entered
    And Eurostat's limits are picked, then PPS, then our limits again
    Then the other-household fields show
    And the ranges in euros follow from our limits for that size, then from Eurostat's
    And in PPS they follow from Eurostat's limits in PPS
    And back on our limits they follow from ours in PPS, or, with no PPS for our year, PPS is greyed with its reason and the ranges are in euros
    """
    site.open(PAGE.format(lang="en"))
    assert not site.find("[data-income-role=other]").is_displayed()
    _choose(site, "household", "other")
    site.visible("[data-income-role=other]")
    _set_number(site, '#income input[name="older"]', 4)
    _set_number(site, '#income input[name="children"]', 3)
    size = equivalent_size(4, 3)
    _same(site, _expected("en", size, "eur"))
    _choose(site, "income-source", "eurostat")
    _same(site, _expected("en", size, "eur", "eurostat"))
    _choose(site, "income-unit", "pps")
    _same(site, _expected("en", size, "pps", "eurostat"))
    _choose(site, "income-source", "ours")
    if cutoffs()["top_cutoffs_pps"] is None:
        # No conversion for our year yet: PPS is greyed with its reason, and the table is in euros.
        site.wait(lambda _: not site.find('input[name="income-unit"][value="pps"]').is_enabled())
        site.visible("[data-income-role=pps-none]")
        _same(site, _expected("en", size, "eur"))
    else:
        _same(site, _expected("en", size, "pps"))


def test_income_panel_starts_from_our_limits_and_says_how_they_are_made(site):
    """SEL-GRP-010: the income panel starts from our limits and says how they are made

    Given the published limits, ours and Eurostat's
    When the Groups page opens
    Then our limits are picked, and Eurostat's can be picked
    And a note gives our limits' survey year, income year and range of standard errors
    And a note gives Eurostat's survey and income years
    And if both are for the same income year, the poorest fifth's limits are compared in numbers, with the gap in percent
    """
    ours, eu = cutoffs(), cutoffs("eurostat")
    site.open(PAGE.format(lang="en"))
    assert site.find('input[name="income-source"][value="ours"]').is_selected()
    assert site.find('input[name="income-source"][value="eurostat"]').is_enabled()
    ses = [v for v in ours["se"].values() if v is not None]
    site.text("[data-income-role=ours-note]", t("en", "income.source.ours_note", survey=ours["survey_year"],
              income=ours["income_year"], se_from=eur(min(ses)), se_to=eur(max(ses))))
    site.text("[data-income-role=eurostat-note]", t("en", "income.source.eurostat_note", survey=eu["survey_year"],
              income=eu["income_year"]))
    if eu["income_year"] == ours["income_year"]:
        # The gap between the two sources is shown in numbers, whichever way it goes.
        a, b = eu["top_cutoffs"]["Q1"], ours["top_cutoffs"]["Q1"]
        diff = t("en", "income.compare.lower" if a <= b else "income.compare.higher", pct=pct("en", abs(a - b) / b * 100))
        site.text("[data-income-role=compare]", t("en", "income.source.compare", income=ours["income_year"],
                  eurostat=eur(a), ours=eur(b), diff=diff))


# --- household types ----------------------------------------------------------------------------

def _household(site, older, children, dependents):
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    _set_number(site, "[data-find=older]", older)
    _set_number(site, "[data-find=children]", children)
    _set_number(site, "[data-find=dependents]", dependents)


@pytest.mark.parametrize("older,children,dependents", [(3, 0, 0), (3, 0, 1), (1, 1, 0)])
def test_finder_names_the_household_type(site, older, children, dependents):
    """SEL-GRP-011: the finder names the household type

    Given the group finder
    When people aged 14 or over, children and dependants among the older ones are entered, with at least one adult
    Then the household's type is named
    """
    kind = household_type(older, children, dependents)
    assert kind is not None, "each example here has an adult"
    _household(site, older, children, dependents)
    site.text("[data-find=type-value]", t("en", f"group.hhtype/{kind}"))


def test_finder_shows_no_type_when_nobody_is_an_adult(site):
    """SEL-GRP-013: the finder shows no household type when nobody counts as an adult

    Given the group finder
    When two people aged 14 or over are entered, both dependants, and no children
    Then no household type is shown

    The survey has no type for a household without an adult, so the finder names none.
    """
    assert household_type(2, 0, 2) is None
    _household(site, 2, 0, 2)
    site.wait(lambda _: not site.find("[data-find=type-row]").is_displayed(), "a household type is shown")


def test_household_section_shows_each_types_share(site):
    """SEL-GRP-012: the household section shows each type's share

    Given the published household-type file
    When the Groups page opens
    Then each type's share of households and its count are shown
    And the comparison link carries every type, in the file's order
    """
    types = data("household-types.json")
    site.open(PAGE.format(lang="en"))
    for k, v in types["groups"].items():
        site.text(f'#household [data-household-share="{k}"]', pct("en", v["share"] * 100))
        site.text(f'#household [data-household-n="{k}"]', v["households"])
    href = site.find("#household [data-household-compare]").get_attribute("href")
    assert href.split("groups=")[1].replace("%2F", "/").replace("%2C", ",").split(",") == list(types["groups"])


def test_finder_without_an_income(site):
    """SEL-GRP-014: without an income, the finder shows no income group and offers three start links

    Given the group finder, with no income entered
    When owning the home is picked, and a pension is not the main income
    Then no income group is shown
    And it offers three links to start from
    """
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    _choose(site, "home", "owner")
    _choose(site, "pension", "no")
    site.wait(lambda _: len(site.all("[data-find=starts] a")) == 3, "the finder doesn't offer three start links")
    assert not site.find("[data-find=income-row]").is_displayed()
