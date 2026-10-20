"""ELSTAT's published HBS table 1.03, both layouts, and the V2 comparison logic."""

from pathlib import Path

import pytest

from traceconomics.checks import FormatError
from traceconomics.sources.elstat.hbs_tables import ALL, parse

FIX = Path(__file__).parent / "fixtures"


def test_old_layout_2018():
    t = parse(FIX / "elstat_hbs_t103_2018.xls", 2018)
    assert t.households[ALL] == pytest.approx(4_085_310)
    assert t.purchases["00"][ALL] == pytest.approx(1442.35)             # the blank-coded "TOTAL PURCHASES" row
    assert t.purchases["01111"][ALL] > 0 and "01111" in t.labels       # leading zeros kept
    assert any(c.startswith("10") for c in t.purchases)                 # division 10, stored as numbers in this file
    assert len(t.groups) == 9 and t.groups[1].startswith("up 750")


def test_new_layout_2024():
    t = parse(FIX / "elstat_hbs_t103_2024.xlsx", 2024)
    assert t.households[ALL] == pytest.approx(4_298_999)
    assert t.purchases["00"][ALL] == pytest.approx(1724.54)
    assert t.purchases["07242"][ALL] == pytest.approx(17.81)
    assert not t.anomalies


def test_year_must_match_what_the_table_says():
    with pytest.raises(FormatError, match="says 2024"):
        parse(FIX / "elstat_hbs_t103_2024.xlsx", 2023)


def test_v2_logic_on_a_tiny_survey():
    pd = pytest.importorskip("pandas")
    from traceconomics.local import v2
    from traceconomics.local.puf import Survey
    from traceconomics.sources.elstat.hbs_tables import Table103

    hh = pd.DataFrame({"hh": ["1", "2"], "weight": [1.0, 3.0]})
    purchases = pd.DataFrame({"01": [120.0, 240.0], "07": [12.0, 0.0], "072": [12.0, 0.0]})  # annual euros
    survey = Survey(2016, "coicop1999-gr", hh, pd.DataFrame(), purchases, purchases, "full", "x")
    table = Table103(2016, [ALL], households={ALL: 4.0},
                     purchases={"00": {ALL: 18.0}, "01": {ALL: 17.5}, "07": {ALL: 0.75},
                                "072": {ALL: 0.75}, "07242": {ALL: 0.5}})
    # 01: (120 + 3 * 240) / 4 / 12 = 17.5 matches. 07242 (0.50 published) is absent from the
    # survey, so 07 and 072 come out at 12 / 4 / 12 = 0.25 instead of 0.75, and 00 is short too:
    # all four are excused by the one missing item, and nothing else is.
    r = v2.compare(survey, table, missing={"07242": [2016]})
    assert r.matched == 1 and [e[0] for e in r.excused] == ["00", "07", "072", "07242"] and r.passed
    r = v2.compare(survey, table, missing={"07242": [2015]})       # listed for another year only
    assert not r.passed and {m[0] for m in r.mismatches} == {"00", "07", "072", "07242"}
