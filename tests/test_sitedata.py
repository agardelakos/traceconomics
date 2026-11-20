"""The made-up site data (`tests/sitedata.py`), which the site's browser tests run on: it goes
through the real export, and takes the same special paths as real baskets do."""

import json

import duckdb
import pytest
import sitedata

from traceconomics.export import site
from traceconomics.module1 import combinations

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """(the site data folder, the work folder with the store and module 1's outputs)."""
    out, work = tmp_path_factory.mktemp("data"), tmp_path_factory.mktemp("work")
    sitedata.generate(out, work, log=lambda *a: None)
    return out, work


@pytest.fixture(scope="module")
def data(generated):
    return generated[0] / "v1" / "gr" / "m1" / "latest"


def test_every_setting_gets_its_files_and_the_shared_ones_are_there(data):
    """PY-SITEDATA-001: every setting gets its files, and the shared ones are there

    Given the made-up site data generated through the real export
    When its files are listed
    Then every setting has a series file and a contributions file
    And the calculator, availability, official, settings and metadata files and SHA256SUMS are there
    And the COICOP labels and the references file are there
    """
    for s in combinations.settings():
        slug = site.slug(s)
        assert (data / "series" / f"{slug}.json").is_file() and (data / "contributions" / f"{slug}.json").is_file()
    for name in (
        "calculator.json",
        "availability.json",
        "official.json",
        "settings.json",
        "metadata.json",
        "SHA256SUMS",
    ):
        assert (data / name).is_file()
    assert (data.parents[2] / "labels" / "coicop18.json").is_file() and (data.parents[2] / "references.json").is_file()


def test_the_country_card_rates_are_for_the_same_month_and_agree(data):
    """PY-SITEDATA-002: the country card's two rates are for the same month and agree

    Given the made-up site data, whose published rates are made from its own overall index
    When its official rate file is read
    Then our rate and the published one are for the same month
    And they differ by no more than the agreement tolerance, and the comparison says they agree
    And the two rates the card shows, to one decimal, are equal

    The made-up published rates are computed from the made-up index, as ELSTAT's come from the
    index it publishes, so a gap here means the export changed how one side is read.
    """
    official = json.loads((data / "official.json").read_text(encoding="utf-8"))
    computed, published = official["computed"], official["published"]
    assert computed["period"] == published["period"] == official["comparison"]["period"]
    assert abs(computed["annual_rate_full"] - published["annual_rate_full"]) <= site.AGREE
    assert official["comparison"]["agree"] is True
    assert computed["annual_rate"] == published["annual_rate"]


def test_made_up_baskets_take_the_special_paths(data):
    """PY-SITEDATA-003: the made-up baskets take the special paths

    Given the made-up site data's weights-used downloads
    When they are read for three settings
    Then a small cell is published in a "_REST" row
    And with imputed rent, 0421 is priced with actual rents (0411)
    And tutoring (1050), with no index of its own, is priced with secondary education (1020)
    """
    con = duckdb.connect()

    def used(setting, where):
        path = (data / "downloads" / setting / "m1_weights_used.parquet").as_posix()
        return set(con.execute(f"SELECT DISTINCT coicop18, priced_with FROM '{path}' WHERE {where}").fetchall())

    # a small cell published inside "rest of" its parent; imputed rent priced with actual rents;
    # tutoring (no index of its own) priced with secondary education
    assert any(c.endswith("_REST") for c, _ in used("all_excluded_cpi_N_priced", "true"))
    assert used("purchases_included_cpi_N_priced", "coicop18 = '0421'") == {("0421", "0411")}
    assert used("purchases_excluded_cpi_N_priced", "coicop18 = '1050'") == {("1050", "1020")}


def test_the_hicp_ends_a_month_earlier_and_says_why(data):
    """PY-SITEDATA-004: the made-up HICP ends a month earlier, and the availability table says why

    Given the made-up site data, whose HICP ends a month before the CPI, as the real data do for about a week every month
    When its availability table is read
    Then the HICP's last month is the one before the CPI's last month
    And the HICP is greyed for the CPI's last month with reason "ends_earlier"
    """
    table = json.loads((data / "availability.json").read_text(encoding="utf-8"))
    hicp, cpi = table["options"]["price_source"]["hicp"], table["options"]["price_source"]["cpi"]
    assert cpi["index"][1] == f"{sitedata.LAST}-{sitedata.LAST_MONTH:02d}"
    assert hicp["index"][1] == f"{sitedata.LAST}-{sitedata.HICP_LAST_MONTH:02d}"
    assert [(g["reason"], g["index"]) for g in hicp["greyed"]] == [("ends_earlier", [cpi["index"][1]] * 2)]


def _last(block: dict) -> str:
    return max(p for year in block.values() for series in year.values() for p in series)


@pytest.mark.parametrize("state", list(sitedata.STATES))
def test_each_data_state_ends_where_it_says(state):
    """PY-SITEDATA-005: each made-up data state's prices and surveys end where the state says

    Given one of the made-up data states (HICP behind, HICP caught up, January, a new survey year)
    When the module is set to it and its price blocks and baskets are made
    Then the CPI's and the HICP's last months are the state's
    And the baskets cover exactly the state's survey years
    And afterwards the module is back on the default state
    """
    want = sitedata.STATES[state]
    try:
        sitedata.use_state(state)
        assert _last(sitedata.blocks()) == "{}-{:02d}".format(*want["last"])
        assert _last(sitedata.blocks(hicp=True)) == "{}-{:02d}".format(*want["hicp_last"])
        surveys = {h for kept in sitedata.baskets().values() for h, _, _ in kept}
        assert surveys == set(want["surveys"])
    finally:
        sitedata.use_state(sitedata.DEFAULT_STATE)
    assert (sitedata.LAST, sitedata.LAST_MONTH, sitedata.HICP_LAST) == (2026, 9, (2026, 8))


def test_generate_goes_back_to_the_default_state_even_on_failure(tmp_path, monkeypatch):
    """PY-SITEDATA-006: generating another state or value set leaves the module on the defaults, even when it fails

    Given a generation for the January state and the second value set that fails part way (the price blocks raise)
    When it is run
    Then the error comes through
    And the module is back on the default state and values, so later tests in the same process see the usual data
    """

    def broken(**_):
        raise RuntimeError("made to fail")

    monkeypatch.setattr(sitedata, "blocks", broken)
    with pytest.raises(RuntimeError, match="made to fail"):
        sitedata.generate(tmp_path / "out", tmp_path / "work", log=lambda *a: None, state="january", values="b")
    assert (sitedata.LAST, sitedata.LAST_MONTH, sitedata.SURVEYS) == (2026, 9, range(2008, 2025))
    assert (sitedata.SALT, sitedata.SCALE) == ("", 1.0)


def test_the_made_up_outputs_pass_the_weights_check(generated):
    """PY-SITEDATA-007: the made-up outputs pass the build's weights check

    Given the made-up module 1 outputs and store (surveys 2008-2024, data to 2026-09)
    When the build's weights check runs on them
    Then it finds no problem: 2026 uses survey 2023 as a first estimate (survey 2024's public file came out in 2026), as rule N gives
    """
    from traceconomics.module1 import weights_check
    from traceconomics.store.query import open_views

    _, work = generated
    con = duckdb.connect()
    open_views(con, work / "store")
    held = weights_check.held_surveys(con)
    assert held == set(sitedata.SURVEYS)
    assert weights_check.check(work / "outputs" / "gr" / "m1", held) == []


def test_the_second_value_set_changes_every_kind_of_number():
    """PY-SITEDATA-008: the second value set gives the same shapes with other numbers of every kind

    Given the made-up generator's usual values and its second value set
    When a price index, a basket share, an income limit and its error, a group count and a household-type share are made in each
    Then each differs between the sets, while the months, codes and groups are the same
    And the usual values are back afterwards
    """

    def sample():
        counts = list(sitedata._group_count_rows())
        types = [v for _, d, y, v in counts if d.get("grouping") == "hhtype" and d["measure"] == "households_weighted"]
        limits = list(sitedata._limit_rows())
        b = sitedata.basket(2020, "B", "Q1", spending="purchases", imputed_rent="excluded")
        return {
            "index": sitedata.level("0111", 2022, 4),
            "share": round(b.shares["011"], 6),
            "limit": limits[0][3],
            "se": limits[1][3],
            "count": counts[0][3],
            "types": [round(v / sum(types[:6]), 4) for v in types[:6]],
            "keys": ([(ds, tuple(d.items()), y) for ds, d, y, _ in limits], sorted(b.shares)),
        }

    a = sample()
    sitedata.use_values("b")
    try:
        b = sample()
    finally:
        sitedata.use_values(sitedata.DEFAULT_VALUES)
    assert a["keys"] == b["keys"]
    for kind in ("index", "share", "limit", "se", "count", "types"):
        assert a[kind] != b[kind], kind
    assert sample() == a
