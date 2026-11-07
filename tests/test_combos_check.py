"""The checks on every combination (`traceconomics check combos`), on module 1 outputs written by the
real writer from the made-up prices and baskets of the site's browser tests (tests/sitedata.py).

The outputs hold the default setting and the one-change settings the reports compare it with, each
with both tutoring options, so they build in seconds rather than the minute all 48 settings take."""

import json
import shutil

import duckdb
import pytest

import sitedata
from traceconomics.module1 import availability, combinations, combos_check as cc, output

pytestmark = pytest.mark.integration

D = combinations.DEFAULT
# The tutoring identity compares every priced setting with its excluded twin, so each comes in both.
SETTINGS = [s | {"tutoring": t} for s in (D, D | {"price_source": "hicp"}, D | {"imputed_rent": "included"},
                                         D | {"weights_timing": "F"}, D | {"weights_timing": "U"})
            for t in ("priced", "excluded")]
GROUPS = [("all", "all")] + [("B", f"Q{k}") for k in range(1, 6)] + [("tenure", "renter")]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Module 1's outputs folder (gr/m1) for SETTINGS and GROUPS."""
    folder = tmp_path_factory.mktemp("outputs") / "gr" / "m1"
    writer, summaries = output.Writer(folder), []
    for _, series, used in combinations.iterate(None, None, only=SETTINGS, groups=GROUPS,
                                                blocks={"cpi": sitedata.blocks(), "hicp": sitedata.blocks(hicp=True)},
                                                baskets=sitedata.baskets()):
        writer.add(series, used)
        summaries += [availability.Summary.of(s) for s in series]
    writer.close()
    availability.write(folder, availability.build(summaries))
    return folder


@pytest.fixture
def outputs(built, tmp_path):
    """A copy of the built outputs, free to change."""
    return shutil.copytree(built, tmp_path / "m1")


def rewrite(folder, table, assignment, condition):
    """Change some rows of one output file in place; returns how many rows changed."""
    path = (folder / f"{table}.parquet").as_posix()
    con = output.parquet_connection()
    con.execute(f"CREATE TABLE t AS SELECT * FROM '{path}'")
    changed = con.execute(f"SELECT count(*) FROM t WHERE {condition}").fetchone()[0]
    con.execute(f"UPDATE t SET {assignment} WHERE {condition}")
    con.execute(f"COPY (SELECT * FROM t) TO '{path}' (FORMAT parquet)")
    return changed


def verdicts(results):
    return {name: ok for name, ok, _ in results}


def test_the_identities_hold_on_outputs_written_by_the_real_code(built):
    """PY-COMBO-010: every identity holds on outputs written by the real writer

    Given module 1 outputs for the default and its one-change settings, each with both tutoring options
    When the identities are checked against the same outputs as the earlier build
    Then the tutoring options agree before 2026
    And the contributions add up to the annual rates
    And every written series is in the availability table, and the other way round
    And the default equals the earlier build
    """
    results = cc.identities(built, built)
    assert verdicts(results) == {"tutoring options before 2026": True, "contributions add up": True,
                                 "availability table": True, "default against the earlier build": True}
    detail = dict((name, text) for name, _, text in results)
    assert detail["availability table"] == f"{len(SETTINGS) * len(GROUPS)} series, all listed"


def test_a_tutoring_difference_before_2026_breaks_its_identity(outputs):
    """PY-COMBO-011: a difference between the tutoring options before 2026 breaks their identity

    Given module 1 outputs where one 2020 annual-average rate differs between the tutoring options
    When the identities are checked
    Then the tutoring identity fails and names the rates file
    And the contributions and availability identities still hold
    """
    n = rewrite(outputs, "m1_rates", "value_text = value_text || '9'",
                f"{cc.where(tutoring='excluded')} AND unit = 'RCH_A_AVG' AND ref_period = '2020' AND grouping = 'all'")
    assert n == 1
    results = cc.identities(outputs)
    assert verdicts(results) == {"tutoring options before 2026": False, "contributions add up": True,
                                 "availability table": True}
    assert "m1_rates" in results[0][2]


def test_contributions_that_dont_add_up_break_their_identity(outputs):
    """PY-COMBO-012: contributions that don't add up to the annual rate break their identity

    Given module 1 outputs where one 2026 contribution of the default's all-households series is 1 pp too high
    When the identities are checked
    Then the contributions identity fails, its largest difference about 1 pp
    And the tutoring identity still holds (the change is after 2025)
    """
    n = rewrite(outputs, "m1_contributions", "value = CAST(CAST(value AS DOUBLE) + 1 AS VARCHAR)",
                f"{cc.where()} AND grouping = 'all' AND unit = 'PC_PNT' AND ref_period = '2026-03' AND coicop18 = '01'")
    assert n == 1
    results = cc.identities(outputs)
    assert verdicts(results)["contributions add up"] is False
    assert verdicts(results)["tutoring options before 2026"] is True
    assert "within 1.0" in results[1][2]


def test_a_series_missing_from_the_availability_table_breaks_its_identity(outputs):
    """PY-COMBO-013: a written series missing from the availability table breaks its identity

    Given module 1 outputs whose availability table leaves out one series
    When the identities are checked
    Then the availability identity fails and names the series written but not listed
    """
    path = outputs / "availability.json"
    table = json.loads(path.read_text(encoding="utf-8"))
    dropped = table["series"].pop(0)
    path.write_text(json.dumps(table), encoding="utf-8")
    ok, text = cc.availability_identity(cc._con(outputs), outputs)
    assert not ok
    assert "written but not listed" in text and dropped["group"] in text.split("listed but not written")[0]


def test_the_default_against_an_earlier_build(built, outputs, tmp_path):
    """PY-COMBO-014: the default is compared with an earlier build, which may hold fewer groups

    Given an earlier build holding only the default's all-households series
    And another earlier build where one of the default's index values differs
    And a third with no rows of the default
    When the current outputs are compared with each
    Then they equal the first
    And differ from the second, naming the index file
    And differ from the third, an earlier build with nothing to compare being a failure
    """
    fewer = shutil.copytree(built, tmp_path / "fewer")
    for t in ("m1_index", "m1_rates", "m1_contributions"):
        rewrite(fewer, t, "grouping = 'gone'", "grouping <> 'all'")
        con = output.parquet_connection()
        path = (fewer / f"{t}.parquet").as_posix()
        con.execute(f"COPY (SELECT * FROM '{path}' WHERE grouping = 'all') TO '{path}.tmp' (FORMAT parquet)")
        shutil.move(f"{path}.tmp", path)
    assert cc.baseline_identity(cc._con(built), fewer) == (True, "equal to the earlier build")

    assert rewrite(outputs, "m1_index", "value_text = value_text || '9'",
                   f"{cc.where()} AND grouping = 'all' AND ref_period = '2020-01' AND coicop18 = 'TOTAL'") == 1
    ok, text = cc.baseline_identity(cc._con(built), outputs)
    assert not ok and "m1_index" in text

    empty = shutil.copytree(built, tmp_path / "empty")
    for t in ("m1_index", "m1_rates", "m1_contributions"):
        rewrite(empty, t, "spending = 'all'", "true")
    ok, text = cc.baseline_identity(cc._con(built), empty)
    assert not ok and "differs from the earlier build" in text


def _avg(folder, where, unit="RCH_A_AVG"):
    con = duckdb.connect()
    return {int(p): float(v) for p, v in con.execute(
        f"SELECT ref_period, value FROM '{(folder / 'm1_rates.parquet').as_posix()}' WHERE unit = '{unit}' AND {where}").fetchall()}


def test_the_price_source_and_timing_reports(built):
    """PY-COMBO-015: the price-source and timing reports read each setting's own annual averages

    Given module 1 outputs with CPI and HICP prices and the three timing rules
    When the price-source and timing reports are made
    Then the price-source report gives, per year, the all-households average under each price source and the B gap under each
    And the timing report gives the B gap under rules N, F and U, with None where a rule has no figure that year
    """
    src = cc.source(built)
    cpi = _avg(built, cc.where() + " AND grouping = 'all'")
    hicp = _avg(built, cc.where(price_source="hicp") + " AND grouping = 'all'")
    gap = _avg(built, cc.where() + " AND grouping = 'B'", "RCH_A_AVG_GAP")
    assert sorted(src) == sorted(set(cpi) & set(hicp))
    y = max(src)
    assert src[y]["all_cpi"] == cpi[y] and src[y]["all_hicp"] == hicp[y] and src[y]["gap_cpi"] == gap.get(y)
    tm = cc.timing(built)
    assert set(tm[y]) == {"N", "F", "U"} and tm[y]["N"] == gap.get(y)
    u = _avg(built, cc.where(weights_timing="U") + " AND grouping = 'B'", "RCH_A_AVG_GAP")
    assert all(tm[year]["U"] == u.get(year) for year in tm)
    assert any(tm[year]["U"] is None for year in tm)


def test_the_imputed_rent_report(built):
    """PY-COMBO-016: the imputed-rent report gives each group's rent weight and what keeping it changes

    Given module 1 outputs with imputed rent excluded and included
    When the imputed-rent report is made
    Then every group of the B, all-households and tenure groupings is in it
    And each has a positive 2025 imputed-rent weight, except renters, who have none
    And each year's change is the annual average with the rent kept minus the one without it
    """
    r = cc.rent(built)
    assert set(r) == {"all", "Q1", "Q2", "Q3", "Q4", "Q5", "renter"}
    assert r["renter"]["weight_2025"] == 0
    assert all(v["weight_2025"] > 0 for g, v in r.items() if g != "renter")
    keep = _avg(built, cc.where(imputed_rent="included") + " AND \"group\" = 'renter'")
    drop = _avg(built, cc.where() + " AND \"group\" = 'renter'")
    assert r["renter"]["change"] == {y: keep[y] - drop[y] for y in keep if y in drop}


def test_the_tutoring_report(built):
    """PY-COMBO-017: the tutoring report gives the newest month's rate and the education weight under both options

    Given module 1 outputs with tutoring priced and excluded
    When the tutoring report is made
    And it is made for 2026-03
    Then it is for the newest month with an annual rate, in 2026
    And it covers all households and the B quintiles, with the rate under both options
    And excluding tutoring leaves a smaller education weight in 2026 for every group
    And after the second report, it is for 2026-03
    """
    t = cc.tutoring(built)
    assert t["period"].startswith("2026")
    assert set(t["groups"]) == {"all/all"} | {f"B/Q{k}" for k in range(1, 6)}
    for g in t["groups"].values():
        assert {"priced", "excluded"} <= set(g)
        assert g["education_weight_excluded"] < g["education_weight_priced"]
    assert cc.tutoring(built, "2026-03")["period"] == "2026-03"
