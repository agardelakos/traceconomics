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
    weights, prices, official, rates = load()
    results = {r.name: r for r in v1.run(weights, prices, official, rates, last_year=int(max(official)[:4]))}
    # The extract starts in 2014-12, so only the finest-detail run (from 2015) has its base month.
    r = results["finest detail"]
    assert r.passed, r.summary()
    assert r.months >= 100 and r.worst_rate_gap <= 0.1 + 1e-9 and r.worst_link[1] < 1e-3


def test_v1_catches_a_broken_engine():
    weights, prices, official, rates = load()
    # Drop food from every year's basket: the rebuilt index is no longer the official one.
    broken = {y: {c: w for c, w in ws.items() if not c.startswith("01")} for y, ws in weights.items()}
    result = chain(broken, prices, first_year=2015, last_year=int(max(official)[:4]),
                   base_value=official["2014-12"], periods=set(official))
    assert not compare("broken", result, official, rates).passed
