"""Explore: groups, options, measure, gap and view live in the address (defaults left out) and come
back on a reload; controls a view can't use are greyed and say why, and months an option leaves out
are noted with the reason; the summary and the data table show the setting's published series; the
files link and the citation follow the setting; the breakdown view; full screen."""

import pytest
from helpers import BLOCKED, data, default_slug, latest, month, months, num, t

PAGE = "/{lang}/gr/inflation-by-group/explore/"
SETTING_KEYS = ["spending", "imputed_rent", "price_source", "weights_timing", "tutoring"]
DEFAULT_GROUPS = ["Q1", "Q5", "all/all"]


def _defaults():
    s = data("settings.json")
    return {
        "grouping": "B",
        **{k: v for k, v in next(x for x in s["settings"] if x.get("default")).items() if k in s["options"]},
    }


def _slug(options):
    return "_".join(options[k] for k in SETTING_KEYS)


def _key(grouping, g):
    return f"{grouping}/{g}" if g.startswith("Q") else g


def _summary(lang, series, groups, grouping="B", measure="rch_a"):
    """The sentence above the chart, rebuilt from the series file as the page builds it."""
    axis = months(series["start"], series["end"])
    digits = 2 if measure == "index" else 1
    ends = [latest(series["groups"][_key(grouping, g)][measure]) for g in groups]
    last = max(i for i, _ in ends)
    items = [
        t(
            lang,
            "summary.item",
            value=num(lang, v, digits) + ("" if measure == "index" else "%"),
            group=t(lang, f"group.in.{g}"),
        )
        for g, (_, v) in zip(groups, ends)
    ]
    joined = f"{', '.join(items[:-1])} {t(lang, 'summary.and')} {items[-1]}" if len(items) > 1 else items[0]
    if measure == "rch_a":
        return t(lang, "summary.annual", month=month(lang, axis[last], "acc" if lang == "el" else "nom"), list=joined)
    return f"{t(lang, f'explore.measure.{measure}')}, {month(lang, axis[last])}: {joined}."


def _ready(site):
    site.visible("#explore [data-role=summary]")
    site.wait(lambda _: site.find("#explore [data-role=summary]").text != "", "the summary was never written")
    site.hidden("#explore [data-role=loading]")


def _open_options(site):
    fold = site.find("#explore details.fold:has([data-option])")
    if not fold.get_attribute("open"):
        fold.find_element("css selector", "summary").click()


def _pick(site, option, value):
    _open_options(site)
    site.find(f'fieldset[data-option="{option}"] input[value="{value}"]').find_element(
        "xpath", "./ancestor::label"
    ).click()


def _unfold(site, role):
    """Opens the fold (a <details>) that holds the element, as a reader would, and returns it."""
    el = site.find(f"#explore [data-role={role}]")
    fold = el.find_element("xpath", "./ancestor::details[1]")
    if not fold.get_attribute("open"):
        fold.find_element("css selector", "summary").click()
    site.wait(lambda _: el.is_displayed(), f"{role} stayed folded")
    return el


def _chip(site, group):
    return site.find(f'#explore button.chip[data-group="{group}"]')


def _pressed(site):
    return [
        b.get_attribute("data-group")
        for b in site.all("#explore button.chip[data-group]")
        if b.get_attribute("aria-pressed") == "true"
    ]


# --- first load ---------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "el"])
def test_default_view_shows_the_published_series(site, lang):
    """SEL-EXPL-001: the default view shows the published series

    Given Explore, opened with nothing changed
    When it has loaded
    Then the summary gives the latest annual rates of the poorest fifth, the richest fifth and all households, for their month, from the default setting's published series
    And the chart is drawn, its label the same sentence
    And those three groups are picked, and the count says 3 of at most 6
    And it says every option is at its default
    And the address carries only the groups
    """
    site.open(PAGE.format(lang=lang))
    _ready(site)
    assert not site.find("#explore [data-role=noscript]").is_displayed()
    series = data(f"series/{default_slug()}.json")
    expected = _summary(lang, series, DEFAULT_GROUPS)
    site.text("#explore [data-role=summary]", expected)
    assert site.find("#explore [data-role=chart]").get_attribute("aria-label") == expected
    site.scripts_ran("#explore [data-role=chart]")
    assert _pressed(site) == DEFAULT_GROUPS
    site.text("#explore [data-role=group-count]", t(lang, "explore.groups_max", n=3, max=6))
    site.text("#explore [data-role=changed]", t(lang, "option.all_defaults"))
    assert site.query == {"groups": ",".join(DEFAULT_GROUPS)}


def test_table_rows_match_the_series(site):
    """SEL-EXPL-002: the data table matches the published series

    Given Explore with nothing changed
    When the data table is unfolded
    Then its columns are the month, each of the three groups and the gap
    And it has one row per month from the first month with a value
    And its first row (the latest month) and last row (the earliest) hold the published rates and gap, a dash where there is none
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    site.find("#explore [data-role=table-fold] summary").click()
    site.visible("#explore [data-role=table] table")
    series = data(f"series/{default_slug()}.json")
    axis = months(series["start"], series["end"])
    head = [th.text for th in site.all("#explore [data-role=table] thead th")]
    assert head == [t("en", "chart.month"), *[t("en", f"group.{g}") for g in DEFAULT_GROUPS], t("en", "gap")]
    rows = site.all("#explore [data-role=table] tbody tr")
    lines = [series["groups"][_key("B", g)]["rch_a"] for g in DEFAULT_GROUPS]
    first = min(next(i for i, v in enumerate(vals) if v is not None) for vals in lines)
    assert len(rows) == len(axis) - first

    def cells(i):
        values = [vals[i] for vals in lines] + [series["gaps"]["B"]["rch_a"][i]]
        return [axis[i], *["–" if v is None else num("en", v) for v in values]]

    for row, i in ((rows[0], len(axis) - 1), (rows[-1], first)):
        assert [c.text for c in row.find_elements("css selector", "th, td")] == cells(i)


# --- the address --------------------------------------------------------------------------------


@pytest.mark.parametrize("option", SETTING_KEYS + ["grouping"])
def test_each_option_changes_the_address_and_back(site, option):
    """SEL-EXPL-003: each option goes into the address and out again

    Given Explore with nothing changed
    When an option is set to a value other than its default
    And then back to its default
    Then the address carries the option's value, and it says one option is changed
    And at its default the option leaves the address, and it says every option is at its default
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    defaults = _defaults()
    values = {"grouping": ["B", "A", "C"], **data("settings.json")["options"]}[option]
    other = next(v for v in values if v != defaults[option])
    _pick(site, option, other)
    site.url_has(**{option: other})
    site.text("#explore [data-role=changed]", t("en", "option.changed", n=1))
    _pick(site, option, defaults[option])
    site.url_has(**{option: None})
    site.text("#explore [data-role=changed]", t("en", "option.all_defaults"))


def test_option_loads_its_setting_and_follows_in_files_and_citation(site):
    """SEL-EXPL-004: an option loads its setting; the files link and citation follow

    Given Explore with nothing changed
    When the spending option is set to all spending
    Then the summary comes from that setting's published series
    And the files link points to that setting's files on the data page
    And the citation names the option and carries the page's address
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    options = {**_defaults(), "spending": "all"}
    _pick(site, "spending", "all")
    slug = _slug(options)
    expected = _summary("en", data(f"series/{slug}.json"), DEFAULT_GROUPS)
    site.text("#explore [data-role=summary]", expected)
    site.wait(
        lambda _: (
            site.find("#explore [data-role=files-this]").get_attribute("href").endswith(f"/en/data/gr/#setting-{slug}")
        )
    )
    cite = _unfold(site, "cite").text
    assert t("en", "option.spending.all") in cite and site.driver.current_url in cite


def test_files_link_leads_to_the_settings_files(site):
    """SEL-EXPL-005: the files link leads to the setting's files

    Given Explore with nothing changed
    When the link to this setting's files is unfolded and followed
    Then the browser goes to the data page for Greece
    And the default setting's box is open, with files to download
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    _unfold(site, "files-this").click()
    site.wait(lambda _: site.path == "/en/data/gr/")
    box = site.find(f"details#setting-{default_slug()}")
    assert box.get_attribute("open") is not None
    assert box.find_elements("css selector", "a[download]")


def test_the_groups_go_into_the_address(site):
    """SEL-EXPL-006: the groups go into the address

    Given Explore with nothing changed
    When the richest fifth is removed and renters are added
    Then after the removal the address carries the two groups left
    And after the addition it carries renters last
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    _chip(site, "Q5").click()
    site.url_has(groups="Q1,all/all")
    _chip(site, "tenure/renter").click()
    site.url_has(groups="Q1,all/all,tenure/renter")


def test_the_gap_off_goes_into_the_address(site):
    """SEL-EXPL-016: the gap turned off goes into the address

    Given Explore with nothing changed
    When the gap is turned off
    Then the address carries gap=0
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    site.find("#explore [data-role=gap-toggle]").click()
    site.url_has(gap="0")


def test_the_measure_goes_into_the_address_and_the_summary(site):
    """SEL-EXPL-017: the measure goes into the address and the summary

    Given Explore with nothing changed
    When the monthly rate is picked as the measure
    Then the address carries m=rch_m
    And the summary gives the three default groups' monthly rates from the published series
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    site.find('#explore select[data-role=measure] option[value="rch_m"]').click()
    site.url_has(m="rch_m")
    site.text(
        "#explore [data-role=summary]",
        _summary("en", data(f"series/{default_slug()}.json"), DEFAULT_GROUPS, measure="rch_m"),
    )


def test_the_view_goes_into_the_address(site):
    """SEL-EXPL-018: the view goes into the address

    Given Explore with nothing changed
    When the breakdown view is picked
    Then the address carries view=parts
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    site.find('#explore [data-view="parts"]').click()
    site.url_has(view="parts")


def test_reload_restores_the_state(site):
    """SEL-EXPL-007: a reload restores the state

    Given an address asking for all spending, tutoring excluded, three groups, the index as measure and no gap
    When Explore opens
    And the page is reloaded
    Then those groups, the measure, the gap off and both options are picked
    And the summary gives the three groups' index values from that setting's published series
    And after the reload the summary is the same and the address still carries the state
    """
    site.open(PAGE.format(lang="en") + "?spending=all&tutoring=excluded&groups=Q2,Q3,pensioners/other&m=index&gap=0")
    _ready(site)
    assert _pressed(site) == ["Q2", "Q3", "pensioners/other"]
    assert site.js("return document.querySelector('[data-role=measure]').value") == "index"
    assert not site.find("#explore [data-role=gap-toggle]").is_selected()
    assert site.find('input[name="spending"][value="all"]').is_selected()
    assert site.find('input[name="tutoring"][value="excluded"]').is_selected()
    options = {**_defaults(), "spending": "all", "tutoring": "excluded"}
    expected = _summary("en", data(f"series/{_slug(options)}.json"), ["Q2", "Q3", "pensioners/other"], measure="index")
    site.text("#explore [data-role=summary]", expected)
    site.reload()
    _ready(site)
    site.text("#explore [data-role=summary]", expected)
    site.url_has(spending="all", tutoring="excluded", m="index", gap="0")


def test_unknown_values_fall_back_to_defaults(site):
    """SEL-EXPL-008: unknown values in the address fall back to defaults

    Given an address with an unknown spending option, an unknown group beside all households, and an unknown measure and view
    When Explore opens
    Then all households is the only group picked
    And the default spending option is picked
    And the measure is the annual rate, and the chart over time shows, not the breakdown
    And the summary gives all households' latest annual rate from the default setting's series
    And the address keeps only the known group, and drops the spending, measure and view
    """
    site.open(PAGE.format(lang="en") + "?spending=nonsense&groups=Q9,all/all&m=yearly&view=sideways")
    _ready(site)
    assert _pressed(site) == ["all/all"]
    assert site.find(f'input[name="spending"][value="{_defaults()["spending"]}"]').is_selected()
    assert site.js("return document.querySelector('[data-role=measure]').value") == "rch_a"
    site.visible("#explore [data-role=view-time]")
    site.hidden("#explore [data-role=view-parts]")
    site.text("#explore [data-role=summary]", _summary("en", data(f"series/{default_slug()}.json"), ["all/all"]))
    site.url_has(spending=None, m=None, view=None, groups="all/all")


# --- limits and greyed options ------------------------------------------------------------------


def test_at_most_six_groups(site):
    """SEL-EXPL-009: at most six groups

    Given Explore with its three default groups
    When three more fifths are added
    Then the count says 6 of at most 6
    And no other group can be picked
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    for g in ["Q2", "Q3", "Q4"]:
        _chip(site, g).click()
    site.text("#explore [data-role=group-count]", t("en", "explore.groups_max", n=6, max=6))
    free = [b for b in site.all("#explore button.chip[data-group]") if b.get_attribute("aria-pressed") == "false"]
    assert free and all(not b.is_enabled() for b in free), "a seventh group can be picked"


def test_the_last_group_cant_be_removed(site):
    """SEL-EXPL-019: the last group can't be removed

    Given Explore opened with the poorest fifth as its only group
    When the poorest fifth is pressed
    Then it stays picked
    """
    site.open(PAGE.format(lang="en") + "?groups=Q1")
    _ready(site)
    assert _pressed(site) == ["Q1"]
    _chip(site, "Q1").click()
    assert _pressed(site) == ["Q1"], "the last group could be removed"


def test_option_greece_cant_have_is_not_offered(site):
    """SEL-EXPL-010: an option Greece can't have is not offered

    Given Explore with its options unfolded
    When an old link asking for imputed rent by user cost is opened
    Then imputed rent by user cost was not among the choices
    And the address drops it
    """
    # Imputed rent by user cost needs a price index Greece doesn't publish: the method page explains
    # it, Explore doesn't offer it, and an old link asking for it falls back to the default.
    site.open(PAGE.format(lang="en"))
    _ready(site)
    _open_options(site)
    assert not site.all('fieldset[data-option="imputed_rent"] input[value="user_cost"]')
    site.open(PAGE.format(lang="en") + "?imputed_rent=user_cost")
    _ready(site)
    assert "imputed_rent" not in site.query


def test_gap_only_for_the_annual_rate(site):
    """SEL-EXPL-011: the gap is only for the annual rate

    Given Explore with nothing changed
    When the index is picked as the measure
    Then the gap's title showed at first
    And the gap can no longer be turned on, with the reason that it is for the annual rate only
    And the gap's title is hidden
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    assert site.find("#explore [data-role=gap-title]").is_displayed()
    site.find('#explore select[data-role=measure] option[value="index"]').click()
    site.wait(lambda _: not site.find("#explore [data-role=gap-toggle]").is_enabled())
    site.text("#explore [data-role=gap-reason]", t("en", "explore.gap_annual_only"))
    site.hidden("#explore [data-role=gap-title]")


def test_months_an_option_leaves_out_are_noted_with_the_reason(site):
    """SEL-EXPL-015: months an option leaves out are noted, with the reason

    Given Explore with nothing changed, and weights timing rule F, which leaves out months before its first survey
    When rule F is picked
    Then a notice above the chart gives the reason, as the availability file names it
    And the option's own note gives the same reason
    """
    greyed = data("availability.json")["options"]["weights_timing"]["F"]["greyed"]
    reasons = [t("en", f"reason.{g['reason']}") for g in greyed]
    assert reasons, "the data have no months rule F leaves out: nothing to check"
    site.open(PAGE.format(lang="en"))
    _ready(site)
    site.hidden("#explore [data-role=notice]")
    _pick(site, "weights_timing", "F")
    site.visible("#explore [data-role=notice]")
    site.text("#explore [data-role=notice] span", " ".join(reasons))
    note = site.find('fieldset[data-option="weights_timing"] [data-role=note]').text
    assert all(r in note for r in reasons), note


# --- the breakdown view and full screen ---------------------------------------------------------


def test_breakdown_view(site):
    """SEL-EXPL-012: the breakdown view

    Given Explore with the poorest and richest fifths
    When the breakdown view is picked
    Then it shows instead of the chart over time
    And the measure can't be changed, with its reason
    And the title is the one for several groups
    And with more than five categories, five show and a button shows the rest
    And the bars explain the difference
    """
    site.open(PAGE.format(lang="en") + "?groups=Q1,Q5")
    _ready(site)
    site.find('#explore [data-view="parts"]').click()
    site.visible("#explore [data-role=view-parts]")
    site.hidden("#explore [data-role=view-time]")
    assert not site.find("#explore select[data-role=measure]").is_enabled()
    site.text("#explore [data-role=measure-reason]", t("en", "explore.measure_parts"))
    site.text("#explore [data-role=contrib-title]", t("en", "explore.contrib_title_many"))
    rows = site.wait(lambda _: site.all("#explore [data-role=bars] .contrib-row:not(.total)") or False)
    more = site.find("#explore [data-role=contrib-more]")
    if len(rows) > 5:
        assert len([r for r in rows if r.is_displayed()]) == 5
        assert more.get_attribute("aria-expanded") == "false"
        more.click()
        site.wait(lambda _: more.get_attribute("aria-expanded") == "true")
        assert all(r.is_displayed() for r in site.all("#explore [data-role=bars] .contrib-row"))
    assert t("en", "explore.contrib_diff") in site.find("#explore [data-role=bars]").text


def test_full_screen(site):
    """SEL-EXPL-013: full screen

    Given Explore with nothing changed
    When the full screen button is pressed
    And pressed again
    Then the chart's figure fills the screen, and the button offers to leave full screen
    And full screen ends, and the button offers full screen again
    """
    site.open(PAGE.format(lang="en"))
    _ready(site)
    button = site.visible("#explore [data-role=fullscreen]")
    button.click()
    site.wait(
        lambda _: site.js("return document.fullscreenElement?.dataset.role") == "chart-figure",
        "full screen did not start",
    )
    site.attr("#explore [data-role=fullscreen]", "aria-label", t("en", "chart.fullscreen_exit"))
    button.click()
    site.wait(lambda _: site.js("return document.fullscreenElement") is None, "full screen did not end")
    site.attr("#explore [data-role=fullscreen]", "aria-label", t("en", "chart.fullscreen"))


def test_household_types_are_offered_and_drawn_from_the_file(site):
    """SEL-EXPL-014: household types are offered and drawn from the series

    Given an address asking for single adults and two adults with dependent children
    When Explore opens
    Then all six household types are offered as groups
    And the summary gives the two groups' latest annual rates from the published series
    """
    types = ["hhtype/A1", "hhtype/A1_DCH", "hhtype/A2", "hhtype/A2_DCH", "hhtype/A_GE3", "hhtype/A_GE3_DCH"]
    site.open(PAGE.format(lang="en") + "?groups=hhtype/A1,hhtype/A2_DCH")
    _ready(site)
    chips = {b.get_attribute("data-group") for b in site.all("#explore button.chip[data-group]")}
    assert set(types) <= chips
    series = data(f"series/{default_slug()}.json")
    site.text("#explore [data-role=summary]", _summary("en", series, ["hhtype/A1", "hhtype/A2_DCH"]))


def test_gap_note_when_an_end_fifth_isnt_drawn(site):
    """SEL-EXPL-020: the gap note shows when the poorest or richest fifth isn't drawn

    Given an address picking the poorest fifth and all households, but not the richest fifth
    When Explore opens from it
    Then the note about the gap is shown
    """
    site.open(PAGE.format(lang="en") + "?groups=Q1,all/all")
    _ready(site)
    site.visible("#explore [data-role=gap-note]")


def test_one_group_breakdown_title_is_the_sum_of_its_parts(site):
    """SEL-EXPL-022: one group's breakdown title gives its latest rate, the sum of its parts

    Given an address opening the breakdown view for the poorest fifth alone
    When Explore opens from it
    Then the title gives the poorest fifth's latest annual rate: the sum of its categories' parts in the published contributions file
    """
    by_month = data(f"contributions/{default_slug()}.json")["groups"]["B/Q1"]
    total = sum(by_month[max(by_month)].values())  # in the file's order, as the page adds them
    site.open(PAGE.format(lang="en") + "?groups=Q1&view=parts")
    site.visible("#explore [data-role=view-parts]")
    site.text(
        "#explore [data-role=contrib-title]",
        t("en", "explore.contrib_title", group=t("en", "group.in.Q1"), value=f"{num('en', total)}%"),
    )


@pytest.mark.console_errors
def test_data_that_fails_to_load_says_so_and_retry_tries_again(site):
    """SEL-EXPL-021: data that fails to load says so, and Retry tries again

    Given the chart's series files blocked
    When Explore opens
    And the files are unblocked and Retry is pressed
    Then the chart shows an alert saying the data couldn't be loaded, with a Retry button
    And after Retry, the alert goes and the summary is drawn

    The browser logs the refused requests, so this test allows console errors.
    """
    site.driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": BLOCKED + ["*/series/*.json"]})
    try:
        site.open(PAGE.format(lang="en"))
        alert = site.visible("#explore [role=alert]")
        site.wait(lambda _: t("en", "chart.failed") in alert.text, "the alert doesn't say the data failed")
    finally:
        site.driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": BLOCKED})
    retry = next(b for b in site.all("#explore [role=alert] button") if b.text.strip() == t("en", "chart.retry"))
    retry.click()
    site.hidden("#explore [role=alert]")
    site.wait(lambda _: site.find("#explore [data-role=summary]").text != "", "the summary was never drawn after Retry")


def test_a_price_source_that_publishes_later_says_which_month_it_doesnt_have_yet(site):
    """SEL-EXPL-023: a price source that publishes later says which month it doesn't have yet

    Given Explore in each language, and data whose HICP ends a month before the CPI, as for about a week every month
    When the HICP is chosen as the price source
    Then the option's note says the HICP isn't published yet for the CPI's last month, named in that language
    And the chart's summary is written, for the HICP's own last month
    And the page logs no error
    """
    hicp = data("availability.json")["options"]["price_source"]["hicp"]
    greyed = [g for g in hicp["greyed"] if g["reason"] == "ends_earlier"]
    assert len(greyed) == 1, "the data's HICP doesn't end earlier than the CPI: nothing to check"
    for lang in ("en", "el"):
        site.open(PAGE.format(lang=lang))
        _ready(site)
        _pick(site, "price_source", "hicp")
        expected = t(lang, "reason.ends_earlier", month=month(lang, greyed[0]["index"][0], "acc"))
        note = 'fieldset[data-option="price_source"] [data-role=note]'
        site.wait(lambda _: expected in site.find(note).text)
        last = month(lang, hicp["index"][1], "acc" if lang == "el" else "nom")
        site.wait(lambda _: last in site.find("#explore [data-role=summary]").text)
