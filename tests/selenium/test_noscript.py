"""With scripts off (Chrome's own setting), every page still says something true: the parts that
need a script say so and link to the data, forms that can't work stay hidden, and what is written
into the page (headline figures, the income table, menus that are native popovers) still works."""

from helpers import cutoffs, eur, t

GR = "/en/gr/inflation-by-group/"


def test_scripts_are_really_off(noscript):
    noscript.open("/en/")
    assert noscript.find("html").get_attribute("data-theme") is None
    assert not noscript.find(".settings[data-role=theme]").is_displayed(), "the theme control shows without scripts"


def test_explore_says_it_needs_scripts(noscript):
    noscript.open(GR + "explore/")
    line = noscript.find("#explore [data-role=noscript]")
    assert line.is_displayed()
    assert t("en", "explore.noscript") in line.text
    assert line.find_element("css selector", "a").get_attribute("href").endswith("/en/data/gr/")
    for role in ("loading", "view-time", "failed"):
        assert not noscript.find(f"#explore [data-role={role}]").is_displayed(), f"{role} shows without scripts"


def test_calculator_says_it_needs_scripts(noscript):
    noscript.open(GR + "calculator/")
    line = noscript.find("#calculator [data-role=noscript]")
    assert line.is_displayed() and t("en", "calc.noscript") in line.text
    for role in ("loading", "result", "sliders-box", "over-time"):
        assert not noscript.find(f"#calculator [data-role={role}]").is_displayed(), f"{role} shows without scripts"


def test_finder_form_stays_hidden_and_income_table_is_written(noscript):
    noscript.open(GR + "groups/")
    assert noscript.find("[data-find=noscript]").is_displayed()
    assert t("en", "find.noscript") in noscript.find("[data-find=noscript]").text
    assert not noscript.find("[data-find=form]").is_displayed()
    # One adult, in euros: the table the page is built with.
    q1 = cutoffs()["top_cutoffs"]["Q1"]
    assert noscript.find('td[data-income-year="Q1"]').text == t("en", "income.year.upto", amount=eur(q1))
    assert all(td.text for td in noscript.all("td[data-income-year], td[data-income-month]"))


def test_topic_page_shows_its_figures(noscript):
    noscript.open(GR)
    assert "%" in noscript.find("main").text


def test_menus_work_without_scripts(noscript):
    noscript.open("/en/about/")
    label = t("en", "nav.quick", name=t("en", "nav.topics"))
    noscript.find(f'button.nav-arrow[aria-label="{label}"]').click()
    menu = noscript.find("#topic-menu")
    noscript.wait(lambda _: menu.is_displayed(), "the quick list needs a script")


def test_root_offers_the_languages(noscript):
    noscript.open("/")
    assert noscript.path == "/", "the root redirected without a script"
    links = [a.get_attribute("href") for a in noscript.all("main a[lang], a.button[lang]") if a.is_displayed()]
    assert any(h.endswith("/en/") for h in links)
