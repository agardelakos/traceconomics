"""With scripts off (Chrome's own setting), every page still says something true: the parts that
need a script say so and link to the data, forms that can't work stay hidden, and what is written
into the page (headline figures, the income table, menus that are native popovers) still works."""

from helpers import cutoffs, eur, t

GR = "/en/gr/inflation-by-group/"


def test_scripts_are_really_off(noscript):
    """SEL-NOJS-001: scripts are really off

    Given the browser with scripts turned off
    When the English home page opens
    Then no theme has been applied to the page
    And the theme control, which needs a script, is hidden
    """
    noscript.open("/en/")
    assert noscript.find("html").get_attribute("data-theme") is None
    assert not noscript.find(".settings[data-role=theme]").is_displayed(), "the theme control shows without scripts"


def test_explore_says_it_needs_scripts(noscript):
    """SEL-NOJS-002: Explore says it needs scripts

    Given the browser with scripts turned off
    When Explore opens
    Then a line says it needs scripts and links to the Greek data files page
    And the loading message, the chart view and the failure message are hidden
    """
    noscript.open(GR + "explore/")
    line = noscript.find("#explore [data-role=noscript]")
    assert line.is_displayed()
    assert t("en", "explore.noscript") in line.text
    assert line.find_element("css selector", "a").get_attribute("href").endswith("/en/data/gr/")
    for role in ("loading", "view-time", "failed"):
        assert not noscript.find(f"#explore [data-role={role}]").is_displayed(), f"{role} shows without scripts"


def test_calculator_says_it_needs_scripts(noscript):
    """SEL-NOJS-003: the calculator says it needs scripts

    Given the browser with scripts turned off
    When the calculator opens
    Then a line says it needs scripts
    And the loading message, the result, the sliders and the chart over time are hidden
    """
    noscript.open(GR + "calculator/")
    line = noscript.find("#calculator [data-role=noscript]")
    assert line.is_displayed() and t("en", "calc.noscript") in line.text
    for role in ("loading", "result", "sliders-box", "over-time"):
        assert not noscript.find(f"#calculator [data-role={role}]").is_displayed(), f"{role} shows without scripts"


def test_finder_form_stays_hidden_and_income_table_is_written(noscript):
    """SEL-NOJS-004: the finder stays hidden; the income table is written

    Given the browser with scripts turned off
    When the Groups page opens
    Then a line says the finder needs scripts, and its form is hidden
    And the income table shows the poorest fifth's yearly limit for one adult, from the published limits
    And every yearly and monthly cell of the table has text
    """
    noscript.open(GR + "groups/")
    assert noscript.find("[data-find=noscript]").is_displayed()
    assert t("en", "find.noscript") in noscript.find("[data-find=noscript]").text
    assert not noscript.find("[data-find=form]").is_displayed()
    # One adult, in euros: the table the page is built with.
    q1 = cutoffs()["top_cutoffs"]["Q1"]
    assert noscript.find('td[data-income-year="Q1"]').text == t("en", "income.year.upto", amount=eur(q1))
    assert all(td.text for td in noscript.all("td[data-income-year], td[data-income-month]"))


def test_topic_page_shows_its_figures(noscript):
    """SEL-NOJS-005: the topic page shows its figures

    Given the browser with scripts turned off
    When the topic page opens
    Then its content shows figures in percent
    """
    noscript.open(GR)
    assert "%" in noscript.find("main").text


def test_menus_work_without_scripts(noscript):
    """SEL-NOJS-006: menus work without scripts

    Given the browser with scripts turned off, on the About page
    When the arrow next to Topics is pressed
    Then the quick list of topics opens
    """
    noscript.open("/en/about/")
    label = t("en", "nav.quick", name=t("en", "nav.topics"))
    noscript.find(f'button.nav-arrow[aria-label="{label}"]').click()
    menu = noscript.find("#topic-menu")
    noscript.wait(lambda _: menu.is_displayed(), "the quick list needs a script")


def test_root_offers_the_languages(noscript):
    """SEL-NOJS-007: the root offers the languages

    Given the browser with scripts turned off
    When the site's root address opens
    Then it stays at the root instead of redirecting
    And it shows a link to the English pages
    """
    noscript.open("/")
    assert noscript.path == "/", "the root redirected without a script"
    links = [a.get_attribute("href") for a in noscript.all("main a[lang], a.button[lang]") if a.is_displayed()]
    assert any(h.endswith("/en/") for h in links)


def test_a_terms_explanation_opens_without_scripts(noscript):
    """SEL-NOJS-008: without scripts, a term's explanation still opens, with its link

    Given a browser with scripts turned off, on the method page
    When the first explained term is pressed
    Then its explanation opens
    And the explanation shows its link

    The explanation is a popover the browser opens itself, so it needs no script.
    """
    noscript.open("/en/gr/inflation-by-group/method/")
    button = noscript.visible(".term-wrap button.term")
    pop = noscript.find(f'[id="{button.get_attribute("popovertarget")}"]')
    button.click()
    noscript.wait(lambda _: noscript.popover_open(pop), "the explanation did not open")
    assert pop.find_element("css selector", "a").is_displayed(), "the explanation shows no link"
