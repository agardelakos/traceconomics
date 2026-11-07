"""V1 on a committed Greek extract: the engine must rebuild the official all-items HICP."""

from pathlib import Path

import duckdb

from traceconomics.engine import chain
from traceconomics.validate import v1
from traceconomics.validate.compare import compare

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
    result = chain(broken, prices, first_year=2015, last_year=int(max(official)[:4]),
                   base_value=official["2014-12"], periods=set(official))
    assert not compare("broken", result, official, rates).passed
