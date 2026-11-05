"""Explore: groups, options, measure, gap and view live in the address (defaults left out) and come
back on a reload; greyed options can't be picked and say why; the summary and the data table show
the setting's published series; the files link and the citation follow the setting; the
breakdown view; full screen."""

import pytest

from helpers import data, default_slug, latest, month, months, num, t

PAGE = "/{lang}/gr/inflation-by-group/explore/"
SETTING_KEYS = ["spending", "imputed_rent", "price_source", "weights_timing", "tutoring"]
DEFAULT_GROUPS = ["Q1", "Q5", "all/all"]


def _defaults():
    s = data("settings.json")
    return {"grouping": "B", **{k: v for k, v in next(x for x in s["settings"] if x.get("default")).items() if k in s["options"]}}


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
    items = [t(lang, "summary.item", value=num(lang, v, digits) + ("" if measure == "index" else "%"), group=t(lang, f"group.in.{g}"))
             for g, (_, v) in zip(groups, ends)]
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
    site.find(f'fieldset[data-option="{option}"] input[value="{value}"]').find_element("xpath", "./ancestor::label").click()


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
    return [b.get_attribute("data-group") for b in site.all("#explore button.chip[data-group]") if b.get_attribute("aria-pressed") == "true"]


# --- first load ---------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["en", "el"])
def test_default_view_shows_the_published_series(site, lang):
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
    site.open(PAGE.format(lang="en"))
    _ready(site)
    options = {**_defaults(), "spending": "all"}
    _pick(site, "spending", "all")
    slug = _slug(options)
    expected = _summary("en", data(f"series/{slug}.json"), DEFAULT_GROUPS)
    site.text("#explore [data-role=summary]", expected)
    site.wait(lambda _: site.find("#explore [data-role=files-this]").get_attribute("href").endswith(f"/en/data/gr/#setting-{slug}"))
    cite = _unfold(site, "cite").text
    assert t("en", "option.spending.all") in cite and site.driver.current_url in cite


def test_files_link_leads_to_the_settings_files(site):
    site.open(PAGE.format(lang="en"))
    _ready(site)
    _unfold(site, "files-this").click()
    site.wait(lambda _: site.path == "/en/data/gr/")
    box = site.find(f"details#setting-{default_slug()}")
    assert box.get_attribute("open") is not None
    assert box.find_elements("css selector", "a[download]")


def test_groups_measure_gap_and_view_in_the_address(site):
    site.open(PAGE.format(lang="en"))
    _ready(site)
    _chip(site, "Q5").click()
    site.url_has(groups="Q1,all/all")
    _chip(site, "tenure/renter").click()
    site.url_has(groups="Q1,all/all,tenure/renter")
    site.find("#explore [data-role=gap-toggle]").click()
    site.url_has(gap="0")
    measure = site.find("#explore select[data-role=measure]")
    measure.find_element("css selector", 'option[value="rch_m"]').click()
    site.url_has(m="rch_m")
    site.text("#explore [data-role=summary]", _summary("en", data(f"series/{default_slug()}.json"), ["Q1", "all/all", "tenure/renter"], measure="rch_m"))
    site.find('#explore [data-view="parts"]').click()
    site.url_has(view="parts", m="rch_m", gap="0")


def test_reload_restores_the_state(site):
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
    site.open(PAGE.format(lang="en") + "?spending=nonsense&groups=Q9,all/all&m=yearly&view=sideways")
    _ready(site)
    assert _pressed(site) == ["all/all"]
    assert site.find(f'input[name="spending"][value="{_defaults()["spending"]}"]').is_selected()
    site.url_has(spending=None, m=None, view=None, groups="all/all")


# --- limits and greyed options ------------------------------------------------------------------

def test_at_most_six_groups_and_at_least_one(site):
    site.open(PAGE.format(lang="en"))
    _ready(site)
    for g in ["Q2", "Q3", "Q4"]:
        _chip(site, g).click()
    site.text("#explore [data-role=group-count]", t("en", "explore.groups_max", n=6, max=6))
    free = [b for b in site.all("#explore button.chip[data-group]") if b.get_attribute("aria-pressed") == "false"]
    assert free and all(not b.is_enabled() for b in free), "a seventh group can be picked"
    for g in ["Q2", "Q3", "Q4", "Q5", "all/all"]:
        _chip(site, g).click()
    site.wait(lambda _: _pressed(site) == ["Q1"])
    _chip(site, "Q1").click()
    assert _pressed(site) == ["Q1"], "the last group could be removed"


def test_option_greece_cant_have_is_not_offered(site):
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
    site.open(PAGE.format(lang="en"))
    _ready(site)
    assert site.find("#explore [data-role=gap-title]").is_displayed()
    site.find('#explore select[data-role=measure] option[value="index"]').click()
    site.wait(lambda _: not site.find("#explore [data-role=gap-toggle]").is_enabled())
    site.text("#explore [data-role=gap-reason]", t("en", "explore.gap_annual_only"))
    site.hidden("#explore [data-role=gap-title]")


# --- the breakdown view and full screen ---------------------------------------------------------

def test_breakdown_view(site):
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
    site.open(PAGE.format(lang="en"))
    _ready(site)
    button = site.visible("#explore [data-role=fullscreen]")
    button.click()
    site.wait(lambda _: site.js("return document.fullscreenElement?.dataset.role") == "chart-figure", "full screen did not start")
    site.attr("#explore [data-role=fullscreen]", "aria-label", t("en", "chart.fullscreen_exit"))
    button.click()
    site.wait(lambda _: site.js("return document.fullscreenElement") is None, "full screen did not end")
    site.attr("#explore [data-role=fullscreen]", "aria-label", t("en", "chart.fullscreen"))
