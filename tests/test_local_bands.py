"""Error bands for the group series: the vectorised replicates against a plain loop."""

import numpy as np
import pytest

from traceconomics.engine.rates import annual_rate
from traceconomics.local.bands import bands
from traceconomics.module1 import index
from traceconomics.module1.weights_used import Basket


def blocks():
    b = {}
    for y in range(2008, 2027):
        b[y] = {"01": {f"{y - 1}-12": 100.0, **{f"{y}-{m:02d}": 100 + m * (1.0 if y % 2 else 0.2) for m in range(1, 13)}},
                "04": {f"{y - 1}-12": 100.0, **{f"{y}-{m:02d}": 100 + m * 0.5 for m in range(1, 13)}}}
    return b


def test_bands_equal_the_spread_of_series_built_one_replicate_at_a_time():
    b = blocks()
    rng = np.random.default_rng(1)
    reps = 5
    sets, baskets_by_rep = {}, [dict() for _ in range(reps)]
    for h in range(2008, 2025):
        food = rng.uniform(0.3, 0.6, reps)
        shares = np.vstack([food, 1 - food])                    # leaves x replicates
        sets[h] = (["01", "04"], {("B", "Q1"): shares})
        for r in range(reps):
            baskets_by_rep[r][(h, "B", "Q1")] = Basket({"01": food[r], "04": 1 - food[r]}, {"01": "normal", "04": "normal"})
    point = {(h, "B", "Q1"): Basket({"01": 0.45, "04": 0.55}, {"01": "normal", "04": "normal"}) for h in range(2008, 2025)}
    s = index.build(None, "B", "Q1", blocks=b, baskets=point)
    got = bands([s], b, sets, reps).se[("B", "Q1", "RCH_A")]
    one_by_one = [index.build(None, "B", "Q1", blocks=b, baskets=k) for k in baskets_by_rep]
    for period in ("2012-06", "2013-12", "2026-03"):
        rates = [annual_rate(x.chained.index, period) for x in one_by_one]
        assert got[period] == pytest.approx(np.std(rates, ddof=1), rel=1e-9)


def test_years_without_replicates_get_no_band():
    b = blocks()
    point = {(h, "B", "Q1"): Basket({"01": 0.45, "04": 0.55}, {"01": "normal", "04": "normal"}) for h in range(2008, 2025)}
    s = index.build(None, "B", "Q1", blocks=b, baskets=point)
    shares = np.array([[0.4, 0.5, 0.45], [0.6, 0.5, 0.55]])
    sets = {h: (["01", "04"], None if h == 2011 else {("B", "Q1"): shares}) for h in range(2008, 2025)}
    r = bands([s], b, sets, 3)
    assert r.unavailable_years == {("B", "Q1"): {2012}}         # index year 2012 uses survey 2011
    se = r.se[("B", "Q1", "RCH_A")]
    assert "2011-12" in se and "2014-06" in se
    assert not any(p.startswith(("2012", "2013")) for p in se)  # rates that reach back into 2012


def test_bands_for_same_year_weights_and_tutoring_left_out_match_a_plain_loop():
    b = blocks()
    for y in b:
        b[y]["10"] = {f"{y - 1}-12": 100.0, **{f"{y}-{m:02d}": 100 + m * 0.8 for m in range(1, 13)}}
    rng = np.random.default_rng(2)
    reps = 4
    leaves = ["01", "04", "10501"]
    sets, by_rep = {}, [dict() for _ in range(reps)]
    for h in range(2008, 2027):
        food, tut = rng.uniform(0.3, 0.6, reps), rng.uniform(0.01, 0.05, reps)
        shares = np.vstack([food, 1 - food - tut, tut])
        sets[h] = (leaves, {("B", "Q1"): shares})
        for r in range(reps):
            by_rep[r][(h, "B", "Q1")] = Basket(dict(zip(leaves, shares[:, r])), dict.fromkeys(leaves, "normal"))
    point = {(h, "B", "Q1"): Basket({"01": 0.45, "04": 0.52, "10501": 0.03}, dict.fromkeys(leaves, "normal"))
             for h in range(2008, 2027)}
    opts = {"weights_timing": "U", "tutoring": "excluded"}
    s = index.build(None, "B", "Q1", blocks=b, baskets=point, options=opts)
    assert s.schedule[-1].year == 2026 and "10501" not in s.used[2026].weights
    got = bands([s], b, sets, reps).se[("B", "Q1", "RCH_A")]
    one_by_one = [index.build(None, "B", "Q1", blocks=b, baskets=k, options=opts) for k in by_rep]
    for period in ("2012-06", "2025-12", "2026-09"):
        rates = [annual_rate(x.chained.index, period) for x in one_by_one]
        assert got[period] == pytest.approx(np.std(rates, ddof=1), rel=1e-9)
