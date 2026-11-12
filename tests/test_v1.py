"""V1 on a committed Greek extract: the engine must rebuild the official all-items HICP."""

from pathlib import Path

import duckdb
import pytest

from traceconomics.engine import chain
from traceconomics.validate import v1
from traceconomics.validate.compare import compare

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
