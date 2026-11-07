"""Rebuilding other studies' series with their own settings (V4) and the helpers it uses."""

import gzip
import io
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace

import openpyxl
import pytest

from traceconomics.archive.store import Archive
from traceconomics.checks import FormatError
from traceconomics.module1 import attribution, benchmarks
from traceconomics.module1.weights_used import Basket
from storetools import months, store

pytestmark = pytest.mark.unit


def test_kepe_timing_uses_the_same_year_then_two_years_before():
    """PY-BENCH-001: KEPE's timing uses the same year's survey, then the one two years before

    Given index years 2016 to 2025 and surveys 2008 to 2024
    When KEPE's weights timing rule is applied
    Then 2016 and 2017 use their own year's survey
    And from 2022, 2022 uses its own survey and 2023, 2024 and 2025 use the survey two years before
    """
    s = benchmarks.kepe_rule(range(2016, 2026), set(range(2008, 2025)))
    assert [(e.year, e.survey) for e in s][:2] == [(2016, 2016), (2017, 2017)]
    assert [(e.year, e.survey) for e in s if e.year >= 2022] == [(2022, 2022), (2023, 2021), (2024, 2022), (2025, 2023)]


def test_cutting_baskets_to_one_level():
    """PY-BENCH-002: baskets are cut to one level of the tree

    Given a basket with shares at the division, group and subclass levels
    When it is cut to divisions only, and to the group level
    Then the divisions-only basket holds just 01 and 04
    And the group-level basket holds just 011
    """
    b = {(2020, "B", "Q1"): Basket({"01": 0.6, "011": 0.5, "01111": 0.2, "04": 0.4}, {"01": "normal", "04": "normal"})}
    assert benchmarks.divisions_only(b)[(2020, "B", "Q1")].shares == {"01": 0.6, "04": 0.4}
    assert attribution.at_level(b, 3)[(2020, "B", "Q1")].shares == {"011": 0.5}


def test_kepe_figures_are_on_file():
    """PY-BENCH-003: KEPE's published figures are on file

    Given the package's file of KEPE's published figures
    When it is read
    Then chart 1's P20 rate for 2022 is 10.4
    And the text's P20 minus R10 gap for 2022 is 1.9
    """
    pub = benchmarks.kepe_published()
    assert pub["chart1"]["P20"]["2022"] == 10.4 and pub["text"]["P20_minus_R10"]["2022"] == 1.9


# -- Bruegel ------------------------------------------------------------------------------------------

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def _hbs(archive):
    """An archived hbs_str_t223: Greek per-mille shares by quintile, for waves 2015 and 2020."""
    rows = {"QU1": {"CP011": "600", "CP071": "400", "CP042": "300", "CP129": "50", "CP096": "0"},
            "QU5": {"CP011": "200", "CP071": "800"},
            "QU3": {"CP011": "500"}}
    lines = ["freq,quantile,coicop,unit,geo\\TIME_PERIOD\t2015 \t2020 "]
    for q, cells in rows.items():
        lines += [f"A,{q},{code},PM,EL\t1 \t{v} " for code, v in cells.items()]
    lines += ["A,QU1,CP01,PM,EL\t1 \t999 ",          # two digits: not a category
              "A,QU1,CP0111,PM,EL\t1 \t999 ",        # four digits: not a category
              "A,QU1,CP011,PM,CY\t1 \t999 ",         # another country
              "A,QU1,CP011,PC,EL\t1 \t999 ",         # another unit
              "A,QU5,CP012,PM,EL\t1 \t: "]           # no figure
    archive.store_bytes("eurostat", "hbs_str_t223", gzip.compress("\n".join(lines).encode()), url=None,
                        retrieved_at=NOW, ext=".tsv.gz")


def _bruegel(archive, rows):
    """An archived Bruegel dataset: figure 1's data, an xlsx file under an .xls name, in a zip."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "EL"
    ws.append(["country", "date", "bottom", "top", "total", "hicp"])
    for row in rows:
        ws.append(row)
    ws.append(["EL", None, None, None, None, None])           # a blank row at the end
    sheet = io.BytesIO()
    wb.save(sheet)
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as z:
        z.writestr("data_figure1.xls", sheet.getvalue())
    archive.store_bytes("bruegel", "inflation-inequality", zipped.getvalue(), url=None, retrieved_at=NOW, ext=".zip")


def _prices(years=(2022, 2023, 2024)):
    """Greek indices: food (011) up 10% a year, transport (07, no 3-digit index) up 5%, all items up 3%."""
    rows = []
    for k, y in enumerate(years):
        for p in months(y):
            for code, rise in (("01", 1.08), ("011", 1.10), ("07", 1.05), ("TOTAL", 1.03)):
                rows.append(dict(dataset="eurostat:prc_hicp_midx", key=f"M,I15,CP{code},GR", unit="I15", coicop=code,
                                 geo="GR", ref_period=p, value=100.0 * rise ** k))
    return rows


def test_bruegels_weights_are_the_greek_three_digit_shares_of_one_wave(tmp_path):
    """PY-BENCH-004: Bruegel's weights are the Greek three-digit per-mille shares of one survey wave

    Given an archived hbs_str_t223 with Greek and Cypriot rows, two-, three- and four-digit codes, per mille and percent, waves 2015 and 2020
    When the 2020 structure is read for Greece
    Then each quintile has its three-digit per-mille shares of wave 2020, keyed by code without "CP"
    And other levels, other countries, other units and cells without a figure are left out
    And without an archived hbs_str_t223, reading it raises a FormatError
    """
    with pytest.raises(FormatError, match="no archived hbs_str_t223"):
        benchmarks.hbs_structure(Archive(tmp_path))
    archive = Archive(tmp_path)
    _hbs(archive)
    s = benchmarks.hbs_structure(archive)
    assert s == {"QU1": {"011": 600.0, "071": 400.0, "042": 300.0, "129": 50.0, "096": 0.0},
                 "QU5": {"011": 200.0, "071": 800.0}, "QU3": {"011": 500.0}}


def test_bruegels_published_figure_is_read_by_month(tmp_path):
    """PY-BENCH-005: Bruegel's published figure 1 is read month by month

    Given an archived Bruegel dataset whose Greek sheet has two months and a blank row
    When the published figure is read
    Then each series (QU1, QU5, TOTAL, HICP) has both months, keyed "YYYY-MM"
    And the blank row is skipped
    And without an archived dataset, reading it raises a FormatError
    """
    with pytest.raises(FormatError, match="no archived Bruegel dataset"):
        benchmarks.bruegel_published(Archive(tmp_path))
    archive = Archive(tmp_path)
    _bruegel(archive, [["EL", "Jan-23", 8.0, 6.0, 7.0, 3.0], ["EL", "Dec-23", 8.5, 6.5, 7.5, 3.5]])
    pub = benchmarks.bruegel_published(archive)
    assert pub == {"QU1": {"2023-01": 8.0, "2023-12": 8.5}, "QU5": {"2023-01": 6.0, "2023-12": 6.5},
                   "TOTAL": {"2023-01": 7.0, "2023-12": 7.5}, "HICP": {"2023-01": 3.0, "2023-12": 3.5}}


def test_bruegels_method_rebuilt_from_its_inputs(tmp_path):
    """PY-BENCH-006: Bruegel's method weights each category's year-on-year rate by its share

    Given food (011) rising 10% a year and transport, which has only a two-digit index (07), rising 5%
    And quintile 1 spending 600 per mille on food and 400 on transport (071), plus imputed rent, a category with no index and a zero share
    And quintile 5 spending 200 on food and 800 on transport
    When Bruegel's series are rebuilt
    Then only QU1 and QU5 are built
    And transport is priced with its two-digit index
    And imputed rent, the category without an index and the zero share are left out
    And QU1's rate is 8.0% and QU5's 6.0% in every month of 2023 and 2024, with no rate in 2022 (no year before it)
    """
    archive = Archive(tmp_path)
    _hbs(archive)
    out = benchmarks.bruegel_rebuild(store(_prices()), archive)
    assert set(out) == {"QU1", "QU5"}
    assert sorted(out["QU1"]) == months(2023, 2024)
    assert all(v == pytest.approx(8.0) for v in out["QU1"].values())
    assert all(v == pytest.approx(6.0) for v in out["QU5"].values())


def test_v4_compares_bruegel_month_by_month_leaving_out_provisional_months(tmp_path):
    """PY-BENCH-007: V4 compares Bruegel's published series with ours, leaving out months built on provisional data

    Given our rebuilt rates of 8.0% (QU1) and 6.0% (QU5) for every month of 2023 and 2024, and an official all-items rate of 3.0%
    And Bruegel's published figures equal to ours, but QU1 0.3 pp higher in 2024-05
    And Bruegel's own HICP column 3.4% in 2023-12, off the final official rate
    When V4 is run for Bruegel
    Then 2023-12 is listed as provisional and not compared, for both quintiles
    And each quintile compares 23 months
    And QU1 fails: its worst month is 2024-05, 0.3 pp off, beyond the 0.2 pp limit
    And QU5 passes with no gap
    And annual averages are given for 2024 only, the one year with all twelve months compared
    """
    archive = Archive(tmp_path)
    _hbs(archive)
    rows = []
    for p in months(2023, 2024):
        y, m = p.split("-")
        name = list(benchmarks.MONTHS)[int(m) - 1] + "-" + y[2:]
        rows.append(["EL", name, 8.3 if p == "2024-05" else 8.0, 6.0, 7.0, 3.4 if p == "2023-12" else 3.0])
    _bruegel(archive, rows)
    q1, q5 = benchmarks.v4_bruegel(store(_prices()), archive)
    assert (q1.name, q5.name) == ("Bruegel QU1", "Bruegel QU5")
    assert q1.provisional == q5.provisional == ["2023-12"]
    assert q1.months == q5.months == 23
    assert q1.worst_month[0] == "2024-05" and q1.worst_month_gap == pytest.approx(0.3) and not q1.passed
    assert q5.worst_month_gap == pytest.approx(0.0) and q5.passed
    assert list(q1.annual) == [2024] and q1.annual[2024] == (pytest.approx(8.0), pytest.approx(8.025))


def test_an_empty_v4_result_has_no_gap_and_passes():
    """PY-BENCH-008: a V4 result with nothing compared has no gap

    Given a V4 result with no months and no annual averages
    When its gaps are read
    Then both are 0 and it passes
    """
    r = benchmarks.V4Result("nothing")
    assert (r.worst_month_gap, r.worst_annual_gap, r.passed) == (0.0, 0.0, True)


def test_v4_rebuilds_kepe_with_its_settings_and_both_unstated_choices(monkeypatch):
    """PY-BENCH-009: V4 rebuilds KEPE's three groups under both readings of each setting KEPE doesn't state

    Given our series equal to KEPE's published chart for P20 and R20, and 0.1 pp above it for R10
    When KEPE's rebuild is run
    Then there are four variants: purchases or all spending, ranked by people or by households
    And every series is built with KEPE's timing from 2016, on baskets cut to the twelve divisions
    And each variant's largest gap is 0.1 pp and its mean gap one third of that
    And only 2021 to 2024 are kept
    """
    from traceconomics.module1 import index, weights_used

    pub = benchmarks.kepe_published()["chart1"]
    names = {"Q1": "P20", "Q5": "R20", "D10": "R10"}
    calls = []

    def build(con, grouping, label, *, spending, blocks, baskets, rule, first_year):
        calls.append((grouping, label, spending, rule, first_year, sorted({c for b in baskets.values() for c in b.shares})))
        values = {int(y): v + (0.1 if label == "D10" else 0.0) for y, v in pub[names[label]].items()} | {2020: 1.23456}
        return SimpleNamespace(annual_average_rates=lambda: values)
    monkeypatch.setattr(index, "cpi_blocks", lambda con: {})
    monkeypatch.setattr(weights_used, "load_baskets", lambda con, spending: {
        ("B", "Q1", 2016): Basket({"01": 0.5, "011": 0.5, "07": 0.5}, {"01": "A", "011": "A", "07": "A"})})
    monkeypatch.setattr(index, "build", build)
    out = benchmarks.v4_kepe("con")
    assert set(out) == {("purchases", "people"), ("purchases", "households"), ("all", "people"), ("all", "households")}
    assert {c[0] for c in calls} == {"B", "B10", "BH", "BH10"}
    assert all(c[3] is benchmarks.kepe_rule and c[4] == 2016 and c[5] == ["01", "07"] for c in calls)
    for v in out.values():
        assert v["max_gap"] == pytest.approx(0.1) and v["mean_gap"] == pytest.approx(0.1 / 3)
        assert sorted(v["rates"]["P20"]) == [2021, 2022, 2023, 2024]


# -- V5 ------------------------------------------------------------------------------------------

def _series(q1, q5):
    """Stand-ins for the series builder's results: Q1 and Q5 with constant annual averages."""
    return {"Q1": SimpleNamespace(annual_average_rates=lambda: {y: q1 for y in range(2019, 2027)}),
            "Q5": SimpleNamespace(annual_average_rates=lambda: {y: q5 for y in range(2019, 2027)})}


def test_v5_walks_from_bruegel_to_our_default_one_setting_at_a_time(tmp_path, monkeypatch):
    """PY-BENCH-010: V5 walks from Bruegel's published gap to our default, one setting at a time

    Given Bruegel's published QU1 rates 1.5 pp above QU5 in every month of 2020-2023
    And Bruegel's weights, where QU1 is 60% food (up 10% a year) and 40% transport (up 5%), and QU5 20% and 80%
    And our series builder giving a different Q1-Q5 gap for each rung
    When V5 is run against Bruegel
    Then B0 is the published gap, 1.5 pp each year
    And B1, Bruegel's weights chained at December, is 2.0 pp each year (8% against 6%)
    And O3 uses our survey-2020 weights fixed, at three digits, with HICP prices from 2019
    And O2 our yearly weights at three digits, O1 at the finest detail, both with HICP prices and Rule N
    And O0 our default with CPI prices
    And every rung covers 2020 to 2023
    """
    from traceconomics.module1 import index
    from traceconomics.module1.schedule import rule_n

    archive = Archive(tmp_path)
    _hbs(archive)
    rows = []
    for p in months(2020, 2021, 2022, 2023):
        y, m = p.split("-")
        rows.append(["EL", list(benchmarks.MONTHS)[int(m) - 1] + "-" + y[2:], 7.5, 6.0, 7.0, 3.0])
    _bruegel(archive, rows)
    hicp, cpi = {"hicp": True}, {"cpi": True}
    basket = Basket({"01": 1.0, "011": 1.0, "0111": 1.0}, {})
    monkeypatch.setattr(attribution, "load_baskets", lambda con, spending: {
        (y, "B", q): basket for y in range(2019, 2027) for q in ("Q1", "Q5")})
    monkeypatch.setattr(attribution, "hicp_blocks", lambda con: hicp)
    monkeypatch.setattr(index, "price_blocks", lambda con, archive: cpi)

    def build(con, grouping, label, *, blocks, baskets, rule, first_year=None):
        digits = {len(c) for b in baskets.values() for c in b.shares}
        if rule is attribution._same_year:
            assert blocks is hicp and digits == {3} and first_year == 2019
            return _series(4.0, 0.0)[label]
        assert rule is rule_n
        if blocks is cpi:
            return _series(1.0, 0.0)[label]
        return _series(3.0, 0.0)[label] if digits == {3} else _series(2.0, 0.0)[label]
    monkeypatch.setattr(index, "build", build)
    out = attribution.v5_bruegel(store(_prices(range(2018, 2025))), archive)
    expected = {"B0 Bruegel as published": 1.5, "B1 Bruegel weights, chained": 2.0,
                "O3 our survey-2020 weights, 3 digits, fixed, HICP": 4.0,
                "O2 our weights each year (Rule N), 3 digits, HICP": 3.0,
                "O1 the same, finest detail, HICP": 2.0, "O0 our default (CPI prices)": 1.0}
    assert list(out) == list(expected)
    for name, value in expected.items():
        assert sorted(out[name]) == [2020, 2021, 2022, 2023]
        assert all(v == pytest.approx(value) for v in out[name].values()), name


def test_v5_walks_from_kepe_to_our_default(monkeypatch):
    """PY-BENCH-011: V5 walks from KEPE's published gap to our default

    Given our series builder giving a different P20-R20 gap for each rung
    When V5 is run against KEPE
    Then K0 is KEPE's published P20 minus R20 for 2021-2024 (1.5 pp in 2022)
    And K1 uses KEPE's timing from 2016 on the twelve divisions
    And K2 our Rule N on the divisions, and K3 our default at the finest detail
    And each rung covers 2021 to 2024
    """
    from traceconomics.module1 import index
    from traceconomics.module1.schedule import rule_n

    basket = Basket({"01": 1.0, "011": 1.0}, {})
    monkeypatch.setattr(attribution, "load_baskets", lambda con, spending: {("B", "Q1", 2020): basket})
    monkeypatch.setattr(index, "price_blocks", lambda con, archive: {})

    def build(con, grouping, label, *, blocks, baskets, rule, first_year=None):
        divisions = {len(c) for b in baskets.values() for c in b.shares} == {2}
        if rule is benchmarks.kepe_rule:
            assert divisions and first_year == 2016
            return _series(3.0, 0.0)[label]
        assert rule is rule_n
        return _series(2.0, 0.0)[label] if divisions else _series(1.0, 0.0)[label]
    monkeypatch.setattr(index, "build", build)
    out = attribution.v5_kepe("con", "archive")
    assert out["K0 KEPE as published"][2022] == pytest.approx(10.4 - 8.9)
    assert {k: set(v.values()) for k, v in out.items() if not k.startswith("K0")} == {
        "K1 KEPE's settings (same-year weights, divisions)": {3.0}, "K2 our timing (Rule N), divisions": {2.0},
        "K3 our default (finest detail)": {1.0}}
    assert all(sorted(v) == [2021, 2022, 2023, 2024] for v in out.values())
