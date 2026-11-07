"""Module 1's checks against official figures (V3, V6, V-prices, the 2010 seam), on numbers worked
out by hand."""

import gzip
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from traceconomics.archive.store import Archive
from traceconomics.checks import FormatError
from traceconomics.module1 import checks, index
from traceconomics.module1.schedule import elstat_rule
from storetools import months, store

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 1, tzinfo=UTC)
# -- V6 ------------------------------------------------------------------------------------------

def _v6_store():
    """Euro-area division indices: food (01) flat at 100 until 2015, then 110 through 2016;
    drink (02) flat at 100 throughout. Equal item weights in 2015 and 2016."""
    rows = []
    for p in ["2014-12", *months(2015, 2016)]:
        for code, value in (("01", 110.0 if p >= "2016-01" else 100.0), ("02", 100.0)):
            rows.append(dict(dataset="eurostat:prc_hicp_midx", key=f"M,I15,CP{code},EA", unit="I15", coicop=code,
                             geo="EA", ref_period=p, value=value))
        rows.append(dict(dataset="eurostat:prc_hicp_midx", key="M,I15,CP01,DE", unit="I15", coicop="01", geo="DE",
                         ref_period=p, value=999.0))
    for y in (2015, 2016):
        for code in ("01", "02"):
            rows.append(dict(dataset="eurostat:prc_hicp_inw", key=f"A,CP{code},EA", coicop=code, geo="EA",
                             ref_period=str(y), value=500.0))
    return store(rows)


def _ctrb(archive, cells):
    """An archived prc_hicp_ctrb TSV: `cells` is {(coicop, period): text}."""
    periods = months(2016)
    lines = ["freq,unit,coicop,geo\\TIME_PERIOD\t" + "\t".join(periods)]
    for code in ("CP01", "CP02"):
        lines.append(f"M,PC_PNT,{code},EA\t" + "\t".join(cells.get((code, p), ": ") for p in periods))
    lines.append("M,PC_PNT,CP01,DE\t" + "\t".join("9.99 " for _ in periods))       # another country: ignored
    lines.append("M,RCH_A,CP01,EA\t" + "\t".join("9.99 " for _ in periods))        # another unit: ignored
    archive.store_bytes("eurostat", "prc_hicp_ctrb", gzip.compress("\n".join(lines).encode()), url=None,
                        retrieved_at=NOW, ext=".tsv.gz")


def test_v6_rebuilds_eurostats_contributions_and_names_the_worst(tmp_path):
    """PY-MCHK-001: V6 rebuilds Eurostat's euro-area contributions and names the largest difference

    Given euro-area division indices where food rises 10% in January 2016 and drink stays flat, with equal weights
    And Eurostat's published contributions of 5.00 pp for food and 0.00 for drink in every month of 2016
    But 5.03 for food in May and no figure for drink in December
    When V6 is run for 2016
    Then 23 contributions are compared (one has no published figure)
    And 22 are equal at two decimals
    And the worst is food in 2016-05: ours 5.0, Eurostat 5.03
    And another country's and another unit's rows are ignored
    """
    archive = Archive(tmp_path)
    cells = {("CP01", p): "5.00 " for p in months(2016)} | {("CP02", p): "0.00 " for p in months(2016)[:-1]}
    cells[("CP01", "2016-05")] = "5.03 p"
    _ctrb(archive, cells)
    r = checks.v6(_v6_store(), archive, first_year=2016, last_year=2016)
    assert (r.compared, r.exact) == (23, 22)
    period, division, ours, official = r.worst
    assert (period, division, official) == ("2016-05", "01", 5.03) and ours == pytest.approx(5.0)


def test_v6_needs_the_archived_contributions(tmp_path):
    """PY-MCHK-002: V6 refuses to run without Eurostat's archived contributions

    Given euro-area indices and weights in the store but no archived prc_hicp_ctrb
    When V6 is run
    Then a FormatError says to import prc_hicp_ctrb first
    """
    with pytest.raises(FormatError, match="no archived prc_hicp_ctrb"):
        checks.v6(_v6_store(), Archive(tmp_path), first_year=2016, last_year=2016)


# -- V-prices ------------------------------------------------------------------------------------

def test_v_prices_measures_the_gap_between_cpi_and_hicp_item_rates():
    """PY-MCHK-003: V-prices measures, per year, how far the CPI's and the HICP's item rates are apart

    Given CPI and HICP item indices for 2019 and 2020: item 01111 rises 2% in the CPI and 2.05% in the HICP, item 0112 2% and 2.5%
    And a three-digit code and an item only the HICP has
    When V-prices is run
    Then only 2020 is reported (2019 has no year before it)
    And it counts 24 pairs: two items over twelve months
    And half the pairs are within 0.1 pp, the median gap is 0.275 pp and the largest 0.5 pp
    And the three-digit code and the HICP-only item are left out
    """
    rows = []
    for code, cpi, hicp in (("01111", 102.0, 102.05), ("0112", 102.0, 102.5), ("011", 102.0, 150.0)):
        for y in (2019, 2020):
            for p in months(y):
                rows.append(dict(dataset="elstat:cpi07", archive_dataset=f"elstat/doc-{y}", key=f"c={code}", unit="I20",
                                 freq="M", coicop18=code, ref_period=p, value=100.0 if y == 2019 else cpi))
                rows.append(dict(dataset="eurostat:prc_hicp_minr", key=f"M,I25,{code},GR", unit="I25", geo="GR",
                                 coicop18=code, ref_period=p, value=100.0 if y == 2019 else hicp))
    rows += [dict(dataset="eurostat:prc_hicp_minr", key="M,I25,0119,GR", unit="I25", geo="GR", coicop18="0119",
                  ref_period=p, value=100.0) for p in months(2019, 2020)]
    out = checks.v_prices(store(rows))
    assert list(out) == [2020]
    d = out[2020]
    assert d["pairs"] == 24 and d["within_0.1"] == 0.5
    assert d["median"] == pytest.approx(0.275) and d["max"] == pytest.approx(0.5)


# -- V3 ------------------------------------------------------------------------------------------

def test_v3_compares_the_official_cpi_with_both_rungs_year_by_year(monkeypatch):
    """PY-MCHK-004: V3 compares the official CPI with our two rungs year by year

    Given an official CPI flat in 2012 and 1% higher every month of 2013 and 2014
    And our rung L1 (ELSTAT's timing) 1.5% higher in 2013 and missing 2014
    And our rung L2 (our timing) 2% higher in 2013 and 2014
    When V3 is run for purchases
    Then L1 is built from 2012 with ELSTAT's rule, and L2 with ours
    And only 2013 is reported, since 2014 lacks L1
    And its weights effect is L1 minus the official rate (+0.5 pp) and its timing effect L2 minus L1 (+0.5 pp)
    """
    def level(rate):
        return {p: 100.0 * (1 + rate * (p >= "2013")) for p in months(2012, 2013)}
    official = {y: {"TOTAL": {p: 100.0 * (1 + 0.01 * (p >= "2013")) for p in months(y)}} for y in (2012, 2013, 2014)}
    official[2014]["TOTAL"] = {p: 101.0 * 1.01 for p in months(2014)}
    built = []

    def build(con, grouping, group, *, spending, blocks, baskets, rule, first_year=None):
        built.append((rule is elstat_rule, first_year, spending))
        if rule is elstat_rule:
            return SimpleNamespace(index=level(0.015))
        return SimpleNamespace(index=level(0.02) | {p: 102.0 * 1.02 for p in months(2014)})
    monkeypatch.setattr(index, "price_blocks", lambda con, archive: official)
    monkeypatch.setattr(checks, "load_baskets", lambda con, spending: {})
    monkeypatch.setattr(index, "build", build)
    rows = checks.v3("con", "archive", "purchases")
    assert built == [(True, checks.FIRST_L1, "purchases"), (False, None, "purchases")]
    assert [r.year for r in rows] == [2013]
    r = rows[0]
    assert r.official == pytest.approx(1.0) and r.l1 == pytest.approx(1.5) and r.l2 == pytest.approx(2.0)
    assert r.weights_effect == pytest.approx(0.5) and r.timing_effect == pytest.approx(0.5)


# -- the 2010 seam -------------------------------------------------------------------------------

def test_seam_prices_2010_both_ways_with_the_same_weights(monkeypatch):
    """PY-MCHK-005: the seam prices each group's 2010 basket with the original and the re-issued prices

    Given one group whose 2010 weights are half food, half drink
    And ELSTAT's original 2010 prices, where food rises 10% from January to December and drink is flat
    And the re-issued prices, where food rises 4%
    When the seam is measured
    Then the group, named "grouping/group", moves 5% with the original prices and 2% with the re-issued ones
    """
    def prices(food_dec):
        return {2010: {"01": {"2010-01": 100.0, "2010-12": food_dec}, "02": {"2010-01": 100.0, "2010-12": 100.0}}}
    used = SimpleNamespace(weights={"01": 0.5, "02": 0.5}, price_with={})
    monkeypatch.setattr(checks, "cpi_blocks", lambda con: prices(104.0))
    monkeypatch.setattr(index, "price_blocks", lambda con, archive: prices(110.0))
    monkeypatch.setattr(index, "build_all", lambda con, archive: [SimpleNamespace(grouping="B", group="Q1", used={2010: used})])
    out = checks.seam("con", "archive")
    assert list(out) == ["B/Q1"]
    assert out["B/Q1"] == (pytest.approx(5.0), pytest.approx(2.0))
