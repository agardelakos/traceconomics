"""The rescaled bootstrap and the published-CV check, on made-up stratified samples. No real microdata here."""

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from traceconomics.checks import FormatError  # noqa: E402
from traceconomics.local import bootstrap, v2  # noqa: E402
from traceconomics.local.groups import assign  # noqa: E402
from traceconomics.local.puf import Survey  # noqa: E402
from traceconomics.local.shares import PUBLISHED, shares  # noqa: E402

pytestmark = pytest.mark.unit

LEAVES = ("0111", "0411", "0421", "04221", "0451")


def sample(strata=10, areas=6, households=8, design="full", seed=1) -> Survey:
    """A stratified sample of areas; spending varies by area, so areas matter more than households."""
    rng = np.random.default_rng(seed)
    rows, persons, spend = [], [], []
    for s in range(strata):
        for a in range(areas):
            area_food = rng.gamma(4, 300)
            for k in range(households):
                hh = f"{s:02d}{a:02d}{k:02d}"
                income = rng.lognormal(10, 0.6)
                rows.append(
                    {
                        "hh": hh,
                        "weight": 500 + 50 * s + rng.uniform(0, 100),
                        "region": f"EL{s % 3}",
                        "stratum": f"S{s}",
                        "cluster": f"C{s:02d}{a:02d}",
                        "money_income": income,
                        "total_income": income,
                        "main_income_source": "4" if k % 3 == 0 else "1",
                    }
                )
                persons += [(hh, 40)] + [(hh, 10)] * (k % 3)
                renter = k % 4 == 0
                spend.append(
                    {
                        "0111": area_food * rng.uniform(0.5, 1.5) + 0.02 * income,
                        "0411": 4000.0 if renter else 0.0,
                        "0421": 0.0 if renter else 3000.0,
                        "04221": 0.0,
                        "0451": rng.gamma(2, 400),
                    }
                )
    h = pd.DataFrame(rows)
    leaf = pd.DataFrame(spend)
    s = leaf.assign(
        **{
            "011": leaf["0111"],
            "01": leaf["0111"],
            "041": leaf["0411"],
            "0422": leaf["04221"],
            "042": leaf["0421"] + leaf["04221"],
            "045": leaf["0451"],
        }
    )
    s["04"] = s["041"] + s["042"] + s["045"]
    if design == "no-strata":
        h["stratum"] = None
    if design == "no-clusters":
        h["cluster"] = None
    return Survey(
        year=2016,
        classification="ecoicop1",
        households=h,
        persons=pd.DataFrame(persons, columns=["hh", "age"]).assign(relation="1", activity="1"),
        spending=s,
        purchases=s.copy(),
        design=design,
        source_sha256="0" * 64,
    )


def test_factors_keep_each_stratum_whole_and_are_reproducible():
    """PY-BOOT-001: replicate factors keep each stratum whole and are reproducible

    Given a made-up stratified survey of 10 strata with 6 areas each
    When 50 replicate factors are drawn twice from the same seed
    Then both draws are identical
    And in every replicate each stratum's area factors sum to its number of areas (6)
    And every household in an area gets the same factor
    """
    s = sample()
    d = bootstrap.design(s)
    f1 = bootstrap.replicate_factors(d, 50, np.random.default_rng([7, 2016]))
    f2 = bootstrap.replicate_factors(d, 50, np.random.default_rng([7, 2016]))
    assert (f1 == f2).all()
    per_area = pd.DataFrame(f1).groupby(s.households.cluster.to_numpy()).first()
    per_stratum = per_area.groupby(per_area.index.str[:3]).sum()  # n_h - 1 draws x n_h / (n_h - 1)
    assert np.allclose(per_stratum.to_numpy(), 6.0)
    # Every household in an area gets the same factor.
    assert (pd.DataFrame(f1).groupby(s.households.cluster.to_numpy()).nunique() == 1).all().all()


def test_bootstrap_agrees_with_the_linearised_variance_of_a_share():
    """PY-BOOT-002: the bootstrap agrees with the linearised variance of a share

    Given a made-up stratified survey
    And the Taylor-linearised standard error of the food share, without imputed rent
    When standard errors are bootstrapped with 4000 replicates
    Then the design status is "full"
    And the food share's standard error for all households is within 5% of the linearised one
    """
    s = sample()
    w = s.households.weight.to_numpy()
    food = s.spending["0111"].to_numpy()
    total = s.spending[["0111", "0411", "0451"]].sum(axis=1).to_numpy()  # option 1: no imputed rent
    share = (w * food).sum() / (w * total).sum()
    # Taylor linearisation, PSUs with replacement: z = w (y - R x) / X, summed per area.
    z = pd.Series(w * (food - share * total) / (w * total).sum()).groupby(s.households.cluster.to_numpy()).sum()
    strata = z.index.str[:3]
    var = sum(len(g) / (len(g) - 1) * ((g - g.mean()) ** 2).sum() for _, g in z.groupby(strata))
    d, se = bootstrap.standard_errors(s, assign(s), replicates=4000)
    ours = se.set_index(["grouping", "group", "imputed_rent", "code"]).se[("all", "all", 1, "0111")]
    assert d.status == "full"
    assert ours == pytest.approx(np.sqrt(var), rel=0.05)


def test_errors_cover_every_share_and_flag_high_relative_errors():
    """PY-BOOT-003: errors cover every published share and flag high relative errors

    Given a made-up stratified survey, its groups and 200 bootstrap replicates
    When the shares are joined with their errors
    Then groupings used only for validation have no errors
    And every published share has one: positive where the share is positive, zero where it is zero
    And the published groupings are all, A, B, C, tenure, pensioners and hhtype
    And a share is flagged high where its relative error is 0.25 or more, and the flag is empty where the relative error is undefined
    And the design is "full" for every row
    And the food share's error is larger for B/Q1 than for all households, since re-ranking adds uncertainty about who is in a quintile
    """
    s = sample()
    g = assign(s)
    d, se = bootstrap.standard_errors(s, g, replicates=200)
    t = bootstrap.with_errors(shares(s, g), se, d)
    assert t[~t.grouping.isin(PUBLISHED)].se.isna().all()  # validation-only groupings: none
    t = t[t.grouping.isin(PUBLISHED)]
    assert t.se.notna().all() and (t.se[t.share > 0] > 0).all() and (t.se[t.share == 0] == 0).all()
    assert set(t.grouping) == {"all", "A", "B", "C", "tenure", "pensioners", "hhtype"}
    defined = t.rse.notna()
    assert (t.high_rse[defined] == (t.rse[defined] >= 0.25)).all() and t.high_rse[~defined].isna().all()
    assert (t.se_design == "full").all()
    # Re-ranking in each replicate adds uncertainty about who is in a quintile.
    food = t[(t.code == "0111") & (t.imputed_rent == 1)].set_index(["grouping", "group"]).se
    assert food[("B", "Q1")] > food[("all", "all")]


def test_without_areas_there_are_no_errors():
    """PY-BOOT-004: without areas there are no errors

    Given a made-up survey without areas
    When standard errors are computed
    Then the design is "unavailable" and there are no errors
    And its shares joined with them have no errors and design "unavailable"
    """
    s = sample(design="no-clusters")
    d, se = bootstrap.standard_errors(s, assign(s), replicates=10)
    assert d.status == "unavailable" and se.empty
    t = bootstrap.with_errors(shares(s), se, d)
    assert t.se.isna().all() and (t.se_design == "unavailable").all()


def test_without_strata_the_region_stands_in():
    """PY-BOOT-008: without strata the region stands in

    Given a made-up survey without strata
    When its design is read
    Then the design is "approximate" and its strata are the regions
    """
    d = bootstrap.design(sample(design="no-strata"))
    assert d.status == "approximate" and set(d.strata) == {"EL0", "EL1", "EL2"}


def _single_area_stratum(s):
    s.households.loc[s.households.cluster == "C0001", "stratum"] = "lonely"


def _area_in_two_strata(s):
    s.households.loc[0, "stratum"] = "S1"


@pytest.mark.parametrize(
    "break_design, message",
    [
        (_single_area_stratum, "single area"),
        (_area_in_two_strata, "more than one stratum"),
    ],
    ids=["single-area stratum", "area in two strata"],
)
def test_design_refuses_a_single_area_stratum_and_an_area_in_two_strata(break_design, message):
    """PY-BOOT-005: the design refuses a single-area stratum and an area in two strata

    Given a made-up survey where one stratum has a single area, or where one area sits in two strata
    When the design is read
    Then a FormatError says which: a "single area", or "more than one stratum"
    """
    s = sample(strata=2, areas=2, households=3)
    break_design(s)
    with pytest.raises(FormatError, match=message):
        bootstrap.design(s)


@pytest.fixture(scope="module")
def cv_survey():
    """A made-up survey and the coefficients of variation it gives (500 replicates, computed once)."""
    s = sample()
    return s, {c: cv for c, _, cv in v2.cv_check(s, {"00": 1.0, "01": 1.0}, replicates=500).rows}


def test_cv_check_passes_on_our_own_values(cv_survey):
    """PY-BOOT-006: the CV check passes on our own values

    Given a made-up survey and the coefficients of variation it gives
    When they are checked as if published
    Then the check passes
    """
    s, ours = cv_survey
    assert v2.cv_check(s, ours, replicates=500).passed


def test_cv_check_fails_far_from_our_values(cv_survey):
    """PY-BOOT-009: the CV check fails far from our values

    Given a made-up survey and the coefficients of variation it gives
    When a published CV twice ours for division 01 is checked
    Then the check fails
    """
    s, ours = cv_survey
    assert not v2.cv_check(s, {"01": ours["01"] * 2}, replicates=500).passed


def test_limit_errors_come_from_the_same_replicates_and_shrink_with_more_areas():
    """PY-BOOT-007: income-limit errors are reproducible and shrink with more areas

    Given a small and a large made-up stratified survey
    When the standard errors of the income limits are computed with 200 replicates
    And the small survey's are computed again
    Then the small survey's design is "full", with 4 positive errors
    And the large survey's errors are smaller on average
    And the second computation gives the same errors
    """
    from traceconomics.local.bootstrap import limit_errors

    small, big = sample(strata=4, areas=3, households=6), sample(strata=16, areas=8, households=6)
    d, se_small = limit_errors(small, replicates=200)
    _, se_big = limit_errors(big, replicates=200)
    assert d.status == "full" and len(se_small) == 4 and (se_small > 0).all()
    assert se_big.mean() < se_small.mean()
    assert (limit_errors(small, replicates=200)[1] == se_small).all()  # same seed, same errors


def test_without_areas_the_income_limits_have_no_errors():
    """PY-BOOT-010: without areas, the income limits have no standard errors

    Given a made-up survey without areas
    When the standard errors of the income limits are computed
    Then there are none (None)
    """
    from traceconomics.local.bootstrap import limit_errors

    assert limit_errors(sample(design="no-clusters"), replicates=50)[1] is None
