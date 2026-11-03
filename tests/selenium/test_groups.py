"""The Groups page: the group finder (household, income, home, pension -> the reader's groups, with
links to the calculator and Explore) and the income panel (each fifth's income range for a
household, in euros or purchasing power standards). Expected values from the published cut-offs."""

import pytest
from selenium.webdriver.common.keys import Keys

from helpers import cutoffs, equivalent_size, eur, js_round, num, place_income, pps, t

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
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    site.hidden("[data-find=noscript]")
    assert site.find("[data-find=empty]").is_displayed()
    assert not site.find("[data-find=next]").is_displayed()


@pytest.mark.parametrize("lang", ["en", "el"])
@pytest.mark.parametrize("older,children,typed,amount,per", [
    (1, 0, "9000", 9000, "year"),
    (2, 1, "1500", 1500, "month"),
    (2, 2, "45000", 45000, "year"),
    (3, 0, "2.000", 2000, "month"),
])
def test_finder_places_the_income(site, lang, older, children, typed, amount, per):
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
    assert len(starts) == 1 and starts[0].endswith(f"/calculator/?from=B%2F{fifth}")


def test_finder_warns_near_a_limit(site):
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    q2 = cutoffs()["top_cutoffs"]["Q2"]
    _type_income(site, str(round(q2 * 0.98)))      # 2% under the line between the 2nd and 3rd fifths
    site.text("[data-find=income-value]", t("en", "group.Q2"))
    site.text("[data-find=near]", t("en", "find.near", group=t("en", "group.in.Q3")))


def test_finder_home_and_pension_and_links(site):
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    _type_income(site, "12000")
    _choose(site, "home", "renter")
    _choose(site, "pension", "yes")
    site.text("[data-find=home-value]", t("en", "group.tenure/renter"))
    site.text("[data-find=pension-value]", t("en", "group.pensioners/pensioners"))
    fifth, _ = place_income(cutoffs()["top_cutoffs"], 1.0, 12000)
    starts = [a.get_attribute("href").split("?from=")[1] for a in site.all("[data-find=starts] a")]
    assert starts == [f"B%2F{fifth}", "tenure%2Frenter", "pensioners%2Fpensioners"]
    compare = site.find("[data-find=compare]")
    assert compare.get_attribute("href").endswith(f"/explore/?groups={fifth}%2Ctenure%2Frenter%2Cpensioners%2Fpensioners")
    compare.click()
    site.wait(lambda _: site.path == "/en/gr/inflation-by-group/explore/")
    assert site.query["groups"].split(",") == [fifth, "tenure/renter", "pensioners/pensioners"]


def test_finder_start_link_opens_the_calculator_on_that_group(site):
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    _choose(site, "home", "owner")
    site.visible("[data-find=starts] a").click()
    site.wait(lambda _: site.path.endswith("/calculator/"))
    site.wait(lambda _: site.js("return document.querySelector('[data-role=preset]').value") == "tenure/owner")


@pytest.mark.parametrize("typed", ["abc", "1,50,0", "-5", "0"])
def test_finder_ignores_what_is_not_an_income(site, typed):
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    _type_income(site, typed)
    site.visible("[data-find=empty]")
    assert not site.find("[data-find=income-row]").is_displayed()


def test_finder_keeps_out_of_range_counts_in_bounds(site):
    site.open(PAGE.format(lang="en"))
    site.visible("[data-find=form]")
    _set_number(site, "[data-find=older]", 40)      # max 12
    site.text("[data-find=size]", t("en", "income.size", size=num("en", equivalent_size(12, 0))))


# --- the income panel ---------------------------------------------------------------------------

def _expected(lang, size, unit):
    cuts = cutoffs()["top_cutoffs" if unit == "eur" else "top_cutoffs_pps"]
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
    site.open(PAGE.format(lang=lang))
    _choose(site, "household", household)
    size = equivalent_size(older, children)
    site.text("[data-income-role=size]", t(lang, "income.size", size=num(lang, size)))
    _same(site, _expected(lang, size, "eur"))


def test_income_panel_other_size_and_pps(site):
    site.open(PAGE.format(lang="en"))
    assert not site.find("[data-income-role=other]").is_displayed()
    _choose(site, "household", "other")
    site.visible("[data-income-role=other]")
    _set_number(site, '#income input[name="older"]', 4)
    _set_number(site, '#income input[name="children"]', 3)
    size = equivalent_size(4, 3)
    _same(site, _expected("en", size, "eur"))
    _choose(site, "income-unit", "pps")
    _same(site, _expected("en", size, "pps"))


def test_income_panel_offers_only_published_cutoffs(site):
    site.open(PAGE.format(lang="en"))
    assert not site.find('input[name="income-source"][value="ours"]').is_enabled()
    assert site.find('input[name="income-source"][value="eurostat"]').is_selected()
