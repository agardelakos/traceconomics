"""The tenure calibration (renters counted in full) and the tenure check that measures it. On a
made-up survey of twelve households and made-up EU-SILC tables: the real calibration, grouping,
mapping and shares code runs; reading the survey, the store and the prices, and building the
series, are replaced. Never real microdata."""

from datetime import UTC, datetime

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from traceconomics.archive.store import Archive  # noqa: E402
from traceconomics.checks import FormatError  # noqa: E402
from traceconomics.local import bootstrap, calibration as cal, mapping, puf, silc, tenure_check as tc, weights  # noqa: E402
from traceconomics.local.groups import assign  # noqa: E402
from traceconomics.local.puf import Survey, classification  # noqa: E402
from traceconomics.module1 import index  # noqa: E402

pytestmark = pytest.mark.unit

N = 12
TARGET = {"renter": 0.5, "owner": 0.4, "rent_free": 0.1}


def survey(year=2024):
    """Twelve one-person households in 2024, so in COICOP 2018 codes, incomes rising: every third renting
    (300 a year rent), every third owning (400 imputed rent), every third housed free (200 of
    "other imputed rent"); food and transport rising with income; one weight each."""
    h = pd.DataFrame({"hh": [str(i) for i in range(N)], "weight": 1.0, "region": "EL3",
                      "stratum": ["1" if i < N // 2 else "2" for i in range(N)],
                      "cluster": [f"{i % 3}" for i in range(N)],
                      "money_income": [6000.0 + 2000 * i for i in range(N)],
                      "total_income": [6000.0 + 2000 * i for i in range(N)], "main_income_source": "1"})
    kind = [i % 3 for i in range(N)]       # 0 renter, 1 owner, 2 housed free
    leaf = pd.DataFrame({"01110": [100.0 + 10 * i for i in range(N)],
                         "04110": [300.0 if k == 0 else 0.0 for k in kind],
                         "04210": [400.0 if k == 1 else 0.0 for k in kind],
                         "04220": [200.0 if k == 2 else 0.0 for k in kind],
                         "07220": [50.0 + i for i in range(N)]})
    s = mapping.with_parents(leaf)
    persons = pd.DataFrame({"hh": h.hh, "age": 40, "relation": "1", "activity": "1"})
    return Survey(year=year, classification=classification(year), households=h, persons=persons,
                  spending=s, purchases=s.copy(), design="full", source_sha256="0" * 64)


def store_silc(archive, year, renter, owner, rent_free, all_=None):
    """An EU-SILC tenure table in the archive, as `traceconomics silc run` writes it."""
    rows = [{"geo": "GR", "ref_year": year, "tenure": t, "n_households": "100", "households_weighted": v,
             "people_weighted": v, "rent_paid_eur": 0.0, "source_version": "made up"}
            for t, v in (("all", all_ if all_ is not None else renter + owner + rent_free), ("owner", owner),
                         ("renter", renter), ("rent_free", rent_free)) if v is not None]
    archive.store_bytes("oet-local", silc.OUT.format(year=year), weights.to_csv(pd.DataFrame(rows)[silc.COLUMNS], ["made up"]),
                        url=None, retrieved_at=datetime(2026, 1, 1, tzinfo=UTC), ext=".csv", kind="local")


@pytest.fixture
def silc_archive(tmp_path):
    """EU-SILC 2010, 2016, 2021, 2022, 2023: renters 22% to 2022, then 25% (the step to the next census)."""
    a = Archive(tmp_path)
    for year in (2010, 2016, 2021, 2022):
        store_silc(a, year, 22.0, 70.0, 8.0)
    store_silc(a, 2023, 25.0, 69.0, 6.0)
    return a


# -- the target ------------------------------------------------------------------------------------

def test_the_target_spreads_eu_silcs_census_step_over_the_years_between_the_censuses(silc_archive):
    """PY-CALIB-001: the target is EU-SILC's split, plus the step to the 2021 census spread over 2012-2021

    Given EU-SILC at 22% renters, 70% owners, 8% housed free through 2022, then 25%, 69%, 6% in 2023
    When the targets for surveys 2010, 2016, 2021, 2022 and 2023 are worked out
    Then 2010 and 2023 are EU-SILC's own split
    And 2016 carries half the step: 23.5% renters, 69.5% owners, 7% housed free
    And 2021 and 2022 carry all of it: the 2023 split
    And each target names how it was set and which EU-SILC tables it used
    """
    assert cal.target(silc_archive, 2010).shares == pytest.approx({"renter": 0.22, "owner": 0.70, "rent_free": 0.08})
    assert cal.target(silc_archive, 2023).shares == pytest.approx({"renter": 0.25, "owner": 0.69, "rent_free": 0.06})
    t = cal.target(silc_archive, 2016)
    assert t.shares == pytest.approx({"renter": 0.235, "owner": 0.695, "rent_free": 0.07})
    assert "0.5 of its step from 2022 to 2023" in t.basis and len(t.sources) == 3
    for year in (2021, 2022):
        assert cal.target(silc_archive, year).shares == pytest.approx({"renter": 0.25, "owner": 0.69, "rent_free": 0.06})


@pytest.mark.parametrize("year, problem", [
    (2024, "no EU-SILC tenure table for 2024"),
    (2019, r"no households for \['rent_free'\]"),
    (2018, "add up to 0.9"),
], ids=["no table", "a tenure missing", "shares not adding up"])
def test_a_missing_or_broken_eu_silc_table_is_refused(silc_archive, year, problem):
    """PY-CALIB-002: a missing EU-SILC table, or one with a tenure missing or not adding up, is refused

    Given EU-SILC tables where 2019 lacks the housed-free row and 2018's tenures add up to 90 of 100 households
    When the target for 2024 (no table), 2019 or 2018 is worked out
    Then a FormatError names the problem, not a guess
    """
    store_silc(silc_archive, 2019, 22.0, 70.0, None, all_=100.0)
    store_silc(silc_archive, 2018, 22.0, 60.0, 8.0, all_=100.0)
    with pytest.raises(FormatError, match=problem):
        cal.target(silc_archive, year)


# -- the calibration -------------------------------------------------------------------------------

def test_calibration_hits_the_target_keeps_the_total_and_works_per_replicate():
    """PY-CALIB-003: calibration gives each tenure its share, keeps the total, and works column by column

    Given the made-up survey, a third renting, a third owning, a third housed free
    And one more household with no tenure, weight 1
    When its weights are calibrated to 50% renters, 40% owners, 10% housed free
    Then the households with a tenure have those shares and still add up to 12, the factors 1.5, 1.2 and 0.3
    And the household with no tenure keeps its weight
    And two columns of other weights (replicates) are each calibrated to the same shares
    """
    s = survey()
    tenure = pd.Series([*assign(s)["tenure"], pd.NA], dtype="string")
    h = pd.concat([s.households, s.households.iloc[[0]].assign(hh="x")], ignore_index=True)
    out, factors = cal.calibrated(Survey(**{**s.__dict__, "households": h}), tenure, cal.Target(TARGET, "t", TARGET, ()))
    w = out.households.weight.to_numpy(float)
    assert tc.renter_share(w, tenure) == pytest.approx(0.5)
    assert w[:-1].sum() == pytest.approx(12.0) and w[-1] == 1.0
    assert factors == pytest.approx({"renter": 1.5, "owner": 1.2, "rent_free": 0.3})
    rng = np.random.default_rng(1)
    reps = cal.calibrate(rng.uniform(0.5, 2.0, size=(N + 1, 2)), tenure, TARGET)
    for j in range(2):
        assert tc.renter_share(reps[:, j], tenure) == pytest.approx(0.5)
        assert reps[cal.member(tenure, "owner"), j].sum() / reps[:-1, j].sum() == pytest.approx(0.4)


def test_bootstrap_replicates_are_calibrated_again():
    """PY-CALIB-004: each bootstrap replicate's weights are calibrated again, as the survey's were

    Given the made-up survey's tenure and a calibration to 50% renters
    When replicate weights are drawn with and without the calibration
    Then with it, every replicate has renters at 50% of households
    And without it, the replicates' renter shares vary
    """
    s = survey()
    tenure = assign(s)["tenure"]
    w = s.households.weight.to_numpy(float)
    factors = np.random.default_rng(2).uniform(0.0, 2.0, size=(N, 5))
    calibrated = bootstrap.replicate(w, factors, lambda rw: cal.calibrate(rw, tenure, TARGET))
    plain = bootstrap.replicate(w, factors, None)
    assert [tc.renter_share(calibrated[:, j], tenure) for j in range(5)] == pytest.approx([0.5] * 5)
    assert len({round(tc.renter_share(plain[:, j], tenure), 6) for j in range(5)}) > 1


# -- the tenure check ------------------------------------------------------------------------------

@pytest.fixture
def made_up(monkeypatch):
    """Reading a survey gives the made-up one; the target is TARGET."""
    monkeypatch.setattr(puf, "read", lambda archive, year: survey(year))
    monkeypatch.setattr(cal, "target", lambda archive, year: cal.Target(TARGET, "made up", TARGET, ()))


def test_calibration_moves_rent_in_mixed_groups_only(made_up):
    """PY-TENURE-001: calibrating to more renters raises rent's share in mixed groups and leaves each tenure's own basket

    Given the made-up survey, a third of its households renting, and a target of 50% renters
    When its baskets are built on ELSTAT's weights and on the calibrated ones
    Then the renters', owners' and housed-free baskets are the same both ways
    And rent's share of all households' basket rises
    And the year's note gives renters at a third, then a half, the target and how it was set
    """
    wanted = {("all", "all"), ("tenure", "renter"), ("tenure", "owner"), ("tenure", "rent_free")}
    before, after, note = tc.survey_baskets(weights.prepare(None, 2024), wanted)
    for t in ("renter", "owner", "rent_free"):
        assert after[(2024, "tenure", t)].shares == pytest.approx(before[(2024, "tenure", t)].shares)
    rent_before, rent_after = (b[(2024, "all", "all")].shares[tc.RENT] for b in (before, after))
    assert rent_after > rent_before > 0
    assert note["renters_before"] == pytest.approx(1 / 3) and note["renters_after"] == pytest.approx(0.5)
    assert (note["target"], note["basis"]) == (0.5, "made up")


def fake_build(rates_from):
    """A series builder whose annual-average rate in year y+1 is `rates_from(basket of survey y)`,
    December's rate the same plus one."""
    def build(con, grouping, label, *, blocks, baskets, options=None, first_year=None):
        rates = {y + 1: rates_from(b) for (y, g, q), b in baskets.items() if (g, q) == (grouping, label)}
        dec = {f"{y}-12": {"annual": r + 1} for y, r in rates.items()}
        return type("S", (), {"annual_average_rates": lambda self: rates, "rates": lambda self: dec})()
    return build


WANTED = [("all", "all"), ("tenure", "renter"), ("B", "Q1"), ("B", "Q5")]


def test_the_tenure_check_reports_what_the_calibration_changes(made_up, monkeypatch):
    """PY-TENURE-002: the tenure check reports each survey's calibration and the change it makes to each group

    Given the made-up 2024 survey, a target of 50% renters, and stored baskets equal to the calibrated ones
    And a series builder whose rate is a hundred times the basket's rent share the year before
    When the tenure check is run for all households, the renters and quintiles 1 and 5
    Then survey 2024 is reported with renters at a third, then a half, and no gap to the stored baskets
    And all households' 2025 rate rises, in the annual average and in December alike
    And the renters' rate doesn't move, and rent's share is reported both ways
    And the gap's change is quintile 1's change minus quintile 5's
    """
    _, stored, _ = tc.survey_baskets(weights.prepare(None, 2024), set(WANTED))
    monkeypatch.setattr(index, "price_blocks", lambda con, archive: {})
    monkeypatch.setattr(tc, "load_baskets", lambda con, spending: dict(stored))
    monkeypatch.setattr(index, "build", fake_build(lambda b: 100 * b.shares.get(tc.RENT, 0.0)))
    r = tc.run(None, "con", groups_wanted=WANTED)
    note = r["surveys"][2024]
    assert note["renters_before"] == pytest.approx(1 / 3) and note["renters_after"] == pytest.approx(0.5)
    assert note["store_gap"] == 0.0
    change = r["series"]["all/all"][2025]
    assert change["annual_average"] > 0 and change["december"] == change["annual_average"]
    assert r["series"]["tenure/renter"][2025] == {"annual_average": 0.0, "december": 0.0}
    before, after = r["rent_share"]["all/all"][2024]
    assert after > before
    q1, q5 = r["series"]["B/Q1"][2025]["annual_average"], r["series"]["B/Q5"][2025]["annual_average"]
    assert r["gap_change"][2025] == pytest.approx(q1 - q5, abs=0.002)


def test_the_tenure_check_refuses_a_stale_store(made_up, monkeypatch):
    """PY-TENURE-003: the tenure check refuses a store that lacks groups the weights run builds

    Given the made-up 2024 survey and a store holding only all households' basket for it
    When the tenure check is run for all households and quintile 1
    Then a FormatError says groups are missing from the store and to run the weights run
    """
    _, stored, _ = tc.survey_baskets(weights.prepare(None, 2024), {("all", "all")})
    monkeypatch.setattr(index, "price_blocks", lambda con, archive: {})
    monkeypatch.setattr(tc, "load_baskets", lambda con, spending: dict(stored))
    with pytest.raises(FormatError, match="missing from the store: run `weights run`"):
        tc.run(None, "con", groups_wanted=[("all", "all"), ("B", "Q1")])
