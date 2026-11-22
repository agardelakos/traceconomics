"""V1 on a committed Greek extract: the engine must rebuild the official all-items HICP."""

from pathlib import Path

import duckdb
import pytest

from traceconomics.engine import chain
from traceconomics.validate import v1
from traceconomics.validate.compare import behind, compare, repeated_baskets

pytestmark = pytest.mark.integration

FIX = Path(__file__).parent / "fixtures"


def load():
    return v1.load(duckdb.connect(), FIX / "eurostat_v1_gr_minr.tsv.gz", FIX / "eurostat_v1_gr_iw.tsv.gz", "GR")


def test_v1_greece_finest_detail_passes():
    """PY-VONE-001: V1 at the finest detail rebuilds Greece's official HICP

    Given a committed Greek extract of the HICP indices and item weights
    When V1 is run
    Then the finest-detail run passes
    And it covers at least 100 months, its worst annual-rate gap is at most 0.1 and its worst link is off by less than 1e-3

    The extract starts in 2014-12, so only the finest-detail run (from 2015) has its base month.
    """
    weights, prices, official, rates = load()
    results = {r.name: r for r in v1.run(weights, prices, official, rates, last_year=int(max(official)[:4]))}
    # The extract starts in 2014-12, so only the finest-detail run (from 2015) has its base month.
    r = results["finest detail"]
    assert r.passed, r.summary()
    assert r.months >= 100 and r.worst_rate_gap <= 0.1 + 1e-9 and r.worst_link[1] < 1e-3


def test_v1_catches_a_broken_engine():
    """PY-VONE-002: V1 catches a broken engine

    Given the Greek extract with food dropped from every year's basket
    When the index is chained and compared with the official one
    Then the comparison fails
    """
    weights, prices, official, rates = load()
    # Drop food from every year's basket: the rebuilt index is no longer the official one.
    broken = {y: {c: w for c, w in ws.items() if not c.startswith("01")} for y, ws in weights.items()}
    result = chain(
        broken,
        prices,
        first_year=2015,
        last_year=int(max(official)[:4]),
        base_value=official["2014-12"],
        periods=set(official),
    )
    assert not compare("broken", result, official, rates).passed


def test_v1_keeps_every_compared_month():
    """PY-VONE-003: the comparison keeps every month it compared, consistent with its totals

    Given the committed Greek extract
    When V1 is run at the finest detail
    Then it keeps one row per compared month, in period order, before rounding
    And the rows rounded to one decimal give the same count of exact months and the same worst gap as the totals
    """
    weights, prices, official, rates = load()
    r = {x.name: x for x in v1.run(weights, prices, official, rates, last_year=int(max(official)[:4]))}["finest detail"]
    assert len(r.rows) == r.months and [p for p, _, _ in r.rows] == sorted(p for p, _, _ in r.rows)
    gaps = [abs(round(ours, 1) - round(theirs, 1)) for _, ours, theirs in r.rows]
    assert sum(g < 1e-9 for g in gaps) == r.exact
    assert max(gaps) == pytest.approx(r.worst_rate_gap)


def test_module5_labels_the_hicp_rebuild():
    """PY-VONE-004: the published HICP check counts the months that agree and labels the rest as rounding

    Given the committed Greek extract and V1's finest-detail comparison
    When it is turned into the published check
    Then it compares the same months, the same number agree, and every other month is labelled "rounding"
    """
    from traceconomics.module5.rebuilds import from_validation

    weights, prices, official, rates = load()
    r = {x.name: x for x in v1.run(weights, prices, official, rates, last_year=int(max(official)[:4]))}["finest detail"]
    s = from_validation("gr-hicp-rebuilt-items", r, {"source": "a"}, {"source": "b"}, []).summary()
    assert (s["compared"], s["agree"]) == (r.months, r.exact)
    assert set(s["differ"]) <= {"rounding"}


def test_v1_fails_a_year_that_repeats_the_year_befores_weights():
    """PY-VONE-005: V1 fails a year whose item weights repeat the year before's

    Given the committed Greek extract, with its newest year's item weights replaced by the year before's
    When V1 is run
    Then the finest-detail run fails
    And its failures name the newest year as having the same weights as the year before
    """
    weights, prices, official, rates = load()
    last = max(weights)
    stale = {**weights, last: weights[last - 1]}
    r = {x.name: x for x in v1.run(stale, prices, official, rates, last_year=int(max(official)[:4]))}["finest detail"]
    assert not r.passed
    assert f"{last}: the weights are the same as {last - 1}'s (the new year's basket wasn't read)" in r.failures


@pytest.mark.unit
def test_repeated_baskets_names_only_years_in_range_that_repeat():
    """PY-VONE-006: only the years in the checked range that repeat the year before's weights are named

    Given weights for 2012 to 2015 where 2013 repeats 2012 and 2015 repeats 2014
    When years 2014 to 2015 are checked
    Then only 2015 is named
    And checking 2013 to 2015 names 2013 too, the first year of the range
    And checking 2016, a year with no weights, names nothing
    """
    a, b = {"01": 1.0}, {"01": 2.0}
    weights = {2012: a, 2013: dict(a), 2014: b, 2015: dict(b)}
    assert [f[:4] for f in repeated_baskets(weights, 2014, 2015)] == ["2015"]
    assert [f[:4] for f in repeated_baskets(weights, 2013, 2015)] == ["2013", "2015"]
    assert repeated_baskets(weights, 2016, 2016) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "last, newest, fails",
    [("2026-01", "2026-01", False), ("2026-01", None, False), ("2025-12", "2026-01", True), (None, "2026-01", True)],
)
def test_a_check_that_stops_before_the_stores_newest_month_fails(last, newest, fails):
    """PY-VONE-007: a check that stopped before the store's newest month fails

    Given the last month a check reached and the newest month the store holds
    When the two are compared
    Then a check that reached the newest month, or a store with no month, gives no failure
    And a check that stopped earlier, or reached no month, fails, naming both months
    """
    problem = behind(last, newest)
    assert (problem is not None) == fails
    if fails:
        assert f"the store holds {newest}" in problem and (last or "no month") in problem
