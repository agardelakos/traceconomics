"""Error bands for the group series: the vectorised replicates against a plain loop."""

import pytest

pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from traceconomics.engine.rates import annual_rate  # noqa: E402
from traceconomics.local.bands import bands  # noqa: E402
from traceconomics.module1 import index  # noqa: E402
from traceconomics.module1.weights_used import Basket  # noqa: E402

pytestmark = pytest.mark.unit


def blocks():
    b = {}
    for y in range(2008, 2027):
        b[y] = {
            "01": {f"{y - 1}-12": 100.0, **{f"{y}-{m:02d}": 100 + m * (1.0 if y % 2 else 0.2) for m in range(1, 13)}},
            "04": {f"{y - 1}-12": 100.0, **{f"{y}-{m:02d}": 100 + m * 0.5 for m in range(1, 13)}},
        }
    return b


def test_bands_equal_the_spread_of_series_built_one_replicate_at_a_time():
    """PY-BANDS-001: the error bands equal the spread of series built one replicate at a time

    Given made-up price blocks and five replicate baskets per survey year for group B/Q1
    And the point series built from a fixed basket
    When the error bands of the annual rate are computed from the replicate shares
    Then at 2012-06, 2013-12 and 2026-03 the standard error equals the sample standard deviation of the annual rates of the five series built one replicate at a time
    """
    b = blocks()
    rng = np.random.default_rng(1)
    reps = 5
    sets, baskets_by_rep = {}, [dict() for _ in range(reps)]
    for h in range(2008, 2025):
        food = rng.uniform(0.3, 0.6, reps)
        shares = np.vstack([food, 1 - food])  # leaves x replicates
        sets[h] = (["01", "04"], {("B", "Q1"): shares})
        for r in range(reps):
            baskets_by_rep[r][(h, "B", "Q1")] = Basket(
                {"01": food[r], "04": 1 - food[r]}, {"01": "normal", "04": "normal"}
            )
    point = {
        (h, "B", "Q1"): Basket({"01": 0.45, "04": 0.55}, {"01": "normal", "04": "normal"}) for h in range(2008, 2025)
    }
    s = index.build(None, "B", "Q1", blocks=b, baskets=point)
    got = bands([s], b, sets, reps).se[("B", "Q1", "RCH_A")]
    one_by_one = [index.build(None, "B", "Q1", blocks=b, baskets=k) for k in baskets_by_rep]
    for period in ("2012-06", "2013-12", "2026-03"):
        rates = [annual_rate(x.chained.index, period) for x in one_by_one]
        assert got[period] == pytest.approx(np.std(rates, ddof=1), rel=1e-9)


def test_years_without_replicates_get_no_band():
    """PY-BANDS-002: years without replicates get no band

    Given replicate shares for every survey year except 2011
    When the error bands are computed
    Then index year 2012, which uses survey 2011, is reported unavailable for B/Q1
    And the annual rate has a band at 2011-12 and 2014-06
    And no annual rate in 2012 or 2013, which reaches back into 2012, has a band
    """
    b = blocks()
    point = {
        (h, "B", "Q1"): Basket({"01": 0.45, "04": 0.55}, {"01": "normal", "04": "normal"}) for h in range(2008, 2025)
    }
    s = index.build(None, "B", "Q1", blocks=b, baskets=point)
    shares = np.array([[0.4, 0.5, 0.45], [0.6, 0.5, 0.55]])
    sets = {h: (["01", "04"], None if h == 2011 else {("B", "Q1"): shares}) for h in range(2008, 2025)}
    r = bands([s], b, sets, 3)
    assert r.unavailable_years == {("B", "Q1"): {2012}}  # index year 2012 uses survey 2011
    se = r.se[("B", "Q1", "RCH_A")]
    assert "2011-12" in se and "2014-06" in se
    assert not any(p.startswith(("2012", "2013")) for p in se)  # rates that reach back into 2012


def test_bands_for_same_year_weights_and_tutoring_left_out_match_a_plain_loop():
    """PY-BANDS-003: bands with same-year weights and tutoring left out match a plain loop

    Given made-up price blocks including division 10, and four replicate baskets per year to 2026 that include tutoring (10501)
    And the options weights timing "U" and tutoring "excluded"
    When the point series and the error bands are built with those options
    Then the series' last link year is 2026 and its 2026 weights leave out 10501
    And at 2012-06, 2025-12 and 2026-09 the standard error equals the sample standard deviation of the annual rates of the series built one replicate at a time with the same options
    """
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
            by_rep[r][(h, "B", "Q1")] = Basket(
                dict(zip(leaves, shares[:, r], strict=True)), dict.fromkeys(leaves, "normal")
            )
    point = {
        (h, "B", "Q1"): Basket({"01": 0.45, "04": 0.52, "10501": 0.03}, dict.fromkeys(leaves, "normal"))
        for h in range(2008, 2027)
    }
    opts = {"weights_timing": "U", "tutoring": "excluded"}
    s = index.build(None, "B", "Q1", blocks=b, baskets=point, options=opts)
    assert s.schedule[-1].year == 2026 and "10501" not in s.used[2026].weights
    got = bands([s], b, sets, reps).se[("B", "Q1", "RCH_A")]
    one_by_one = [index.build(None, "B", "Q1", blocks=b, baskets=k, options=opts) for k in by_rep]
    for period in ("2012-06", "2025-12", "2026-09"):
        rates = [annual_rate(x.chained.index, period) for x in one_by_one]
        assert got[period] == pytest.approx(np.std(rates, ddof=1), rel=1e-9)


def test_each_survey_is_prepared_once_for_every_spending_and_rent_option(monkeypatch):
    """PY-BANDS-006: a bands run prepares each survey once, and every option's replicates get that survey's calibration

    Given every setting of the options, whose series use surveys 2023 and 2024
    When the bands are run (the survey reading, the replicates and the band arithmetic faked)
    Then each survey is prepared once, not once per spending concept and rent option
    And the replicates for each of the four spending and rent pairs get the same prepared survey
    And their calibration rescales the weights by that survey's own tenure target
    """
    from types import SimpleNamespace

    import pandas as pd

    from traceconomics.local import bands as b
    from traceconomics.module1 import combinations

    prepared, seen = [], []

    def prepare(archive, year):
        prepared.append(year)
        groups = pd.DataFrame({"tenure": ["owner", "renter"]})
        share = 0.25 if year == 2023 else 0.5  # the owners'; renters the rest, nobody housed free
        target = SimpleNamespace(shares={"owner": share, "renter": 1 - share, "rent_free": 0.0})
        return SimpleNamespace(mapped=f"survey {year}", groups=groups, target=target)

    def replicate_leaf_shares(mapped, groups, wanted, spending, replicates, option, calibrate):
        seen.append((mapped, spending, option, tuple(calibrate(np.array([1.0, 1.0]))[:].round(6))))
        return SimpleNamespace(status="full"), [], None

    def iterate(con, archive, only):
        schedule = [SimpleNamespace(survey=2023), SimpleNamespace(survey=2024)]
        return [(s, [SimpleNamespace(schedule=schedule)], {"cpi": {}, "hicp": {}}) for s in only]

    monkeypatch.setattr(b, "prepare", prepare)
    monkeypatch.setattr(b, "replicate_leaf_shares", replicate_leaf_shares)
    monkeypatch.setattr(combinations, "iterate", iterate)
    monkeypatch.setattr(b, "bands", lambda series, blocks, sets, replicates: b.Bands())
    archive = SimpleNamespace(store_bytes=lambda *a, **k: SimpleNamespace(status="stored"))
    b.run(archive, None, replicates=2, log=lambda line: None)
    assert sorted(prepared) == [2023, 2024]
    assert len(seen) == 8  # 2 surveys x 4 spending and rent pairs
    assert {(m, w) for m, _, _, w in seen} == {("survey 2023", (0.5, 1.5)), ("survey 2024", (1.0, 1.0))}
