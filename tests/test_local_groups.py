"""Groups, spending shares and the per-band V2 check, on small made-up surveys. No real microdata here."""

import pytest

pd = pytest.importorskip("pandas")

from traceconomics.local import v2  # noqa: E402
from traceconomics.local.groups import assign, household_size, quintiles, tenure  # noqa: E402
from traceconomics.local.puf import Survey  # noqa: E402
from traceconomics.local.shares import leaves, shares  # noqa: E402
from traceconomics.sources.elstat.hbs_tables import ALL, Table103  # noqa: E402

# Spending codes of the older classification: food, actual rent, imputed rent (owners and
# housed free), energy. Divisions and groups are the sums of the leaves, as in the real files.
LEAVES = ("0111", "0411", "0421", "04221", "0451")


def survey(rows, persons, year=2015) -> Survey:
    """rows: (hh, weight, money income a year, main income source, {leaf code: euros a year})."""
    h = pd.DataFrame({
        "hh": [r[0] for r in rows], "weight": [float(r[1]) for r in rows], "region": "EL3",
        "stratum": None, "cluster": None,
        "money_income": [float(r[2]) for r in rows], "total_income": [float(r[2]) for r in rows],
        "main_income_source": [r[3] for r in rows],
    })
    leaf = pd.DataFrame([{c: float(r[4].get(c, 0)) for c in LEAVES} for r in rows])
    s = leaf.assign(**{
        "011": leaf["0111"], "01": leaf["0111"],
        "041": leaf["0411"], "0422": leaf["04221"], "042": leaf["0421"] + leaf["04221"], "045": leaf["0451"],
    })
    s["04"] = s["041"] + s["042"] + s["045"]
    # persons: (hh, age) or (hh, age, relation, activity); by default a reference person at work.
    p = pd.DataFrame([(*r, "1", "1")[:4] for r in persons], columns=["hh", "age", "relation", "activity"])
    return Survey(year=year, classification="ecoicop1", households=h, persons=p,
                  spending=s, purchases=s.copy(), design="full", source_sha256="0" * 64)


def adults(ids):
    return [(i, 40) for i in ids]


# ---- groups ---------------------------------------------------------------------------------

def test_modified_oecd_scale():
    s = survey([("a", 1, 1, "1", {}), ("b", 1, 1, "1", {}), ("c", 1, 1, "1", {})],
               [("a", 40), ("b", 40), ("b", 38), ("b", 13), ("b", 3), ("c", 12), ("c", 9)])
    size = household_size(s)
    assert size.loc["a"].tolist() == [1, 1.0]
    assert size.loc["b"].tolist() == [4, pytest.approx(1 + 0.5 + 0.3 + 0.3)]   # aged 13 counts as a child
    assert size.loc["c"].tolist() == [2, pytest.approx(1.3)]                    # no adult: the first child counts 1


def test_quintiles_hold_a_fifth_of_the_weight_each():
    q = quintiles(pd.Series(range(10, 0, -1), dtype=float), pd.Series([1.0] * 10), pd.Series(list("abcdefghij")))
    assert q.tolist() == [5, 5, 4, 4, 3, 3, 2, 2, 1, 1]


def test_quintile_ties_are_broken_by_household_id_and_a_straddler_goes_where_its_middle_is():
    value = pd.Series([5.0, 5.0, 1.0, 9.0])
    q = quintiles(value, pd.Series([1.0, 1.0, 2.0, 1.0]), pd.Series(["z", "y", "x", "w"]))
    # Order x (weight 2), y, z, w over a total of 5: middles at 0.2, 0.5, 0.7, 0.9.
    assert q.tolist() == [4, 3, 2, 5]


def test_missing_value_or_weight_gets_no_quintile():
    q = quintiles(pd.Series([1.0, None, 3.0]), pd.Series([1.0, 1.0, 0.0]), pd.Series(["a", "b", "c"]))
    assert q.iloc[0] == 3 and q.iloc[1:].isna().all()      # alone, the household's middle is at 50%


def test_tenure_renter_first_then_owner_then_housed_free():
    s = survey([
        ("a", 1, 1, "1", {"0411": 100, "0421": 50}),     # rent and imputed rent: a renter
        ("b", 1, 1, "1", {"0421": 50}),
        ("c", 1, 1, "1", {"04221": 50}),
        ("d", 1, 1, "1", {"0111": 10}),                  # no rent of any kind
    ], adults("abcd"))
    t = tenure(s)
    assert t[:3].tolist() == ["renter", "owner", "rent_free"] and pd.isna(t[3])


def test_unplaceable_households_are_left_out_of_that_grouping_only():
    rows = [(f"h{i}", 1, 1000 * (i + 1), "4" if i < 4 else "1", {"0111": 100, "0421": 10}) for i in range(10)]
    rows.append(("odd", 1, 500, "", {"0111": 100}))                      # no persons, rent or income source
    g = assign(survey(rows, adults(f"h{i}" for i in range(10))))
    odd = g.iloc[-1]
    assert odd["A"] == "Q1"                                              # A needs only income and weight
    assert pd.isna(odd["B"]) and pd.isna(odd["C"]) and pd.isna(odd["tenure"]) and pd.isna(odd["pensioners"])
    assert odd["all"] == "all"
    assert set(g["B"].dropna()) == {"Q1", "Q2", "Q3", "Q4", "Q5"}         # labels stay "Q1", even next to NA
    assert (g.pensioners == "pensioners").sum() == 4


# ---- shares ---------------------------------------------------------------------------------

def three_households():
    return survey([
        ("a", 2, 6000, "4", {"0111": 300, "0411": 600, "0451": 100}),
        ("b", 1, 30000, "1", {"0111": 200, "0421": 900, "0451": 400}),
        ("c", 1, 50000, "1", {"0111": 500, "04221": 500}),
    ], adults("abc"))


def test_leaves_are_the_finest_codes():
    assert leaves(["00", "01", "011", "0111", "04", "042", "0421", "0422", "04221"]) == ["0111", "0421", "04221"]


def test_shares_are_plutocratic_and_add_up():
    t = shares(three_households())
    everyone = t[(t.grouping == "all")].set_index(["imputed_rent", "code"]).share
    # Weighted spending: food 2*300 + 200 + 500 = 1300; rent 1200; imputed 900 + 500; energy 200 + 400.
    assert everyone[(2, "0111")] == pytest.approx(1300 / 4500)
    assert everyone[(2, "042")] == pytest.approx(1400 / 4500)
    # Option 1 drops imputed rent and rescales the rest.
    assert everyone[(1, "0111")] == pytest.approx(1300 / 3100)
    assert (1, "0421") not in everyone.index and (1, "042") not in everyone.index
    # Every level adds up to 1, and parents are the sums of their leaves.
    for (grouping, group, option), part in t.groupby(["grouping", "group", "imputed_rent"]):
        assert part[part.leaf].share.sum() == pytest.approx(1)
        assert part[part.digits == 2].share.sum() == pytest.approx(1)
    assert everyone[(2, "04")] == pytest.approx(everyone[(2, "041")] + everyone[(2, "042")] + everyone[(2, "045")])


def test_shares_per_group_count_reporting_households():
    t = shares(three_households())
    pens = t[(t.grouping == "pensioners") & (t.group == "pensioners") & (t.imputed_rent == 2)].set_index("code")
    assert pens.loc["0411", "share"] == pytest.approx(0.6)
    assert pens.loc["0411", "n_households"] == 1 and pens.loc["0411", "households_weighted"] == 2
    rest = t[(t.grouping == "pensioners") & (t.group == "other") & (t.imputed_rent == 2)].set_index("code")
    assert rest.loc["0451", "n_reporting"] == 1 and rest.loc["042", "n_reporting"] == 2
    assert set(t.reliability) == {"suppressed"}                             # 3 households: all under 20


@pytest.mark.parametrize("n,tier", [(19, "suppressed"), (20, "flagged"), (49, "flagged"), (50, "normal")])
def test_reliability_tiers(n, tier):
    from traceconomics.local.shares import reliability
    assert reliability(n) == tier


# ---- V2 by band -----------------------------------------------------------------------------

def banded_table(year, groups, households, food):
    return Table103(year=year, groups=[ALL] + groups, households=households,
                    purchases={"0111": food}, labels={"0111": "Bread and cereals"})


def test_income_bands_include_their_top_after_rounding_to_the_euro():
    s = survey([
        ("a", 1, 6000, "1", {"0111": 120}),        # 500 a month
        ("b", 1, 9000, "1", {"0111": 240}),        # 750: still the first band
        ("c", 1, 9006.2, "1", {"0111": 360}),      # 750.52 rounds to 751
        ("d", 1, 24000, "1", {"0111": 480}),
    ], adults("abcd"))
    groups = ["up 750 €", "751-1100 €", "1101 and over €"]
    table = banded_table(2010, groups, {ALL: 4, groups[0]: 2, groups[1]: 1, groups[2]: 1},
                         {ALL: 10.0, groups[0]: 15.0, groups[1]: 30.0, groups[2]: 40.0})
    band = v2.bands(s, table, "income")
    assert band.tolist() == [groups[0], groups[0], groups[1], groups[2]]
    results = [v2.compare(s, table, {}, group=g, members=band == g) for g in groups]
    assert all(r.passed and r.matched == 1 for r in results)


def test_size_bands_and_a_wrong_band_figure_fails():
    s = survey([("a", 1, 1, "1", {"0111": 120}), ("b", 1, 1, "1", {"0111": 240}), ("c", 1, 1, "1", {"0111": 360})],
               [("a", 40), ("b", 40), ("b", 8), ("c", 40), ("c", 39), ("c", 5), ("c", 1)])
    groups = ["1 member", "2 members", "3 members and over"]
    table = banded_table(2013, groups, {ALL: 3, groups[0]: 1, groups[1]: 1, groups[2]: 1},
                         {ALL: 20.0, groups[0]: 10.0, groups[1]: 20.0, groups[2]: 99.0})
    band = v2.bands(s, table, "size")
    assert band.tolist() == groups
    last = v2.compare(s, table, {}, group=groups[2], members=band == groups[2])
    assert not last.passed and last.mismatches == [("0111", "Bread and cereals", 99.0, 30.0)]
    assert v2.compare(s, table, {}).passed


def test_band_count_that_differs_fails():
    s = survey([("a", 1, 6000, "1", {"0111": 120}), ("b", 1, 24000, "1", {"0111": 120})], adults("ab"))
    groups = ["up 750 €", "751-1100 €", "1101 and over €"]
    table = banded_table(2010, groups, {ALL: 2, groups[0]: 1, groups[1]: 0, groups[2]: 3},
                         {ALL: 10.0, groups[0]: 10.0, groups[2]: 10.0})
    band = v2.bands(s, table, "income")
    assert not v2.compare(s, table, {}, group=groups[2], members=band == groups[2]).passed


def test_uncovered_share_counts_absent_items_whole_and_cut_items_in_part():
    s = survey([("a", 1, 1, "1", {"0111": 120}), ("b", 3, 1, "1", {"0111": 240})], adults("ab"))
    s.purchases["07242"] = [12.0, 12.0]                                # tolls, cut: 1 a month in the PUF
    table = Table103(year=2015, groups=[ALL], households={ALL: 4},
                     purchases={"00": {ALL: 100.0}, "0111": {ALL: 17.5}, "12510": {ALL: 2.0}, "07242": {ALL: 4.0}})
    share, gaps = v2.uncovered(s, table, {"12510": [2015], "07242": [2015, 2016], "12610": [2016]})
    assert gaps == {"12510": 2.0, "07242": pytest.approx(3.0)}          # 12610 isn't listed for 2015
    assert share == pytest.approx(0.05)


def test_shares_leave_unplaceable_households_out_of_that_grouping_only():
    rows = [(f"h{i}", 1, 1000 * (i + 1), "1", {"0111": 100, "0411": 50}) for i in range(5)]
    rows.append(("odd", 1, 500, "", {"0111": 900}))                  # no persons, no income source
    t = shares(survey(rows, adults(f"h{i}" for i in range(5))))
    food = t[(t.code == "0111") & (t.imputed_rent == 1)].set_index(["grouping", "group"])
    assert food.loc[("all", "all"), "share"] == pytest.approx(1400 / 1650)
    assert food.loc[("all", "all"), "n_households"] == 6
    assert food.xs("B", level="grouping").n_households.sum() == 5
    assert food.xs("pensioners", level="grouping").n_households.sum() == 5


def test_quintile_matrix_matches_one_column_at_a_time():
    from traceconomics.local.groups import quintile_matrix
    import numpy as np
    value = pd.Series([3.0, 1.0, None, 2.0, 5.0, 4.0, 2.0])
    ids = pd.Series(list("abcdefg"))
    w = np.array([[1, 2], [1, 0], [1, 1], [2, 1], [1, 3], [1, 1], [1, 1]], dtype=float)
    q = quintile_matrix(value, w, ids)
    assert q[2].tolist() == [0, 0]                                      # missing value
    for r in range(2):
        one = quintiles(value, pd.Series(w[:, r]), ids)
        keep = one.notna().to_numpy()
        assert q[keep, r].tolist() == one[keep].astype(int).tolist()


def test_purchases_leave_out_own_production_and_imputed_rent_comes_from_all_modes():
    s = three_households()
    # Household a grew a third of its food: purchases are lower than all modes there.
    s.purchases.loc[0, ["0111", "011", "01"]] = 200.0
    s.purchases[["0421", "04221", "0422", "042"]] = 0.0                  # imputed rent is never bought
    s.purchases["04"] = s.purchases["041"] + s.purchases["045"]
    p = shares(s, spending="purchases")
    a = shares(s, spending="all")
    pick = lambda t, opt, code: t[(t.grouping == "all") & (t.imputed_rent == opt) & (t.code == code)].share.item()
    # Purchases: food 2*200 + 200 + 500 = 1100; rent 1200; energy 600.
    assert pick(p, 1, "0111") == pytest.approx(1100 / 2900)
    assert pick(a, 1, "0111") == pytest.approx(1300 / 3100)
    # Option 2 adds the imputed rent as valued in the survey, in either concept.
    assert pick(p, 2, "042") == pytest.approx(1400 / (1100 + 1200 + 600 + 1400))
    assert pick(a, 2, "042") == pytest.approx(1400 / 4500)


def test_deciles_and_household_rankings():
    from traceconomics.local.groups import quintile_matrix
    import numpy as np
    q = quintile_matrix(pd.Series(range(20), dtype=float), np.ones(20), pd.Series(range(20)), parts=10)[:, 0]
    assert q.tolist() == [k // 2 + 1 for k in range(20)]
    rows = [(f"h{i}", 1, 1000 * (i + 1), "1", {"0111": 100}) for i in range(10)]
    # Big households at the bottom: ranking people puts fewer households in Q1 than ranking households.
    persons = [(f"h{i}", 40) for i in range(10)] + [(f"h{i}", 10) for i in range(3) for _ in range(3)]
    g = assign(survey(rows, persons))
    assert (g.BH == "Q1").sum() == 2 and (g.B == "Q1").sum() == 1
    assert set(g.B10.dropna()) <= {f"D{k}" for k in range(1, 11)} and (g.BH10 == "D10").sum() == 1


# ---- income limits ---------------------------------------------------------------------------

def test_cut_points_are_midpoints_between_neighbouring_households():
    import numpy as np
    from traceconomics.local.groups import cut_points
    value = pd.Series([float(v) for v in range(10, 110, 10)])            # 10, 20, ... 100, two a fifth
    ids = pd.Series(list("abcdefghij"))
    cuts = cut_points(value, np.ones(10), ids)[:, 0]
    assert cuts.tolist() == [25.0, 45.0, 65.0, 85.0]
    # No limit is any household's own value.
    assert not set(cuts) & set(value)


def test_cut_points_skip_households_without_weight_and_follow_each_column():
    import numpy as np
    from traceconomics.local.groups import cut_points
    value = pd.Series([float(v) for v in range(10, 110, 10)])
    ids = pd.Series(list("abcdefghij"))
    w = np.ones((10, 2))
    w[2, 1] = 0                       # in the second column, 30 isn't drawn: the parts move
    cuts = cut_points(value, w, ids)
    assert cuts[:, 0].tolist() == [25.0, 45.0, 65.0, 85.0]
    assert cuts[0, 1] != 25.0 and not np.isnan(cuts[:, 1]).any()


def test_cut_points_ignore_missing_values_and_mark_an_empty_part():
    import numpy as np
    from traceconomics.local.groups import cut_points
    value = pd.Series([10.0, None, 20.0])
    cuts = cut_points(value, np.ones(3), pd.Series(list("abc")))[:, 0]
    assert np.isnan(cuts).any()       # two households can't fill five parts


def test_limits_table_rounds_midpoints_to_the_euro():
    from traceconomics.local.weights import limits_table
    rows = [(f"h{i:02d}", 1, 1000 * (i + 1) + 0.25, "1", {}) for i in range(20)]
    s = survey(rows, adults([r[0] for r in rows]))
    t = limits_table(s, 2015, replicates=0, source_version="test")
    assert t.group.tolist() == ["Q1", "Q2", "Q3", "Q4"] and (t.unit == "EUR_PER_ADULT_EQ_Y").all()
    # Four households a fifth: the limit between the 4th and 5th incomes is (4000.25 + 5000.25) / 2.
    assert t.limit.tolist() == [4500, 8500, 12500, 16500]
    assert t.se.isna().all()          # no replicates asked for


# ---- household types ---------------------------------------------------------------------------

def test_household_types_follow_eurostats_dependent_child_rule():
    from traceconomics.local.groups import household_type
    rows = [(h, 1, 1000, "1", {}) for h in "abcdefg"]
    persons = [
        ("a", 70),                                          # one adult
        ("b", 40), ("b", 15),                               # a parent and a child under 16
        ("c", 40), ("c", 38), ("c", 20, "3", "4"),          # a 20-year-old student, child of the couple
        ("d", 40), ("d", 38), ("d", 20, "3", "1"),          # the same, but working: an adult
        ("e", 40), ("e", 38), ("e", 22, "5", "4"),          # a student who is a nephew: an adult
        ("f", 40), ("f", 38), ("f", 70, "4", "3"), ("f", 25, "3", "4"),   # 25 is past the age limit
        ("g", 10),                                          # no adult at all
    ]
    t = household_type(survey(rows, persons))
    assert t.tolist()[:6] == ["A1", "A1_DCH", "A2_DCH", "A_GE3", "A_GE3", "A_GE3"]
    assert pd.isna(t.iloc[6])


def test_household_types_are_a_grouping_and_unplaced_households_are_left_out():
    rows = [("a", 1, 1000, "1", {"0111": 10}), ("b", 1, 2000, "1", {"0111": 10}), ("c", 1, 3000, "1", {"0111": 10})]
    g = assign(survey(rows, [("a", 40), ("b", 40), ("b", 5)]))       # c has no person records
    assert g.hhtype.tolist()[:2] == ["A1", "A1_DCH"] and pd.isna(g.hhtype.iloc[2])


def test_types_table_compares_with_elstats_type_and_stops_when_far_apart():
    from traceconomics.checks import FormatError
    from traceconomics.local import weights
    rows = [(f"h{i}", 1, 1000, "1", {}) for i in range(10)]
    s = survey(rows, adults([r[0] for r in rows]))
    g = assign(s)
    s.households["elstat_type"] = ["1"] * 9 + ["2"]                   # one of ten disagrees: 90%
    t = weights.types_table(s, g, 2015, "v")
    a1 = t.set_index("group").loc["A1"]
    assert a1.n_households == "<20" and a1.share_households == 1.0 and a1.elstat_share_households == 0.9
    assert t.agreement.iloc[0] == 0.9 and (t.elstat_status == "compared").all()
    s.households["elstat_type"] = ["2"] * 10
    with pytest.raises(FormatError, match="agree with ELSTAT's on 0.0%"):
        weights.types_table(s, g, 2015, "v")
    assert weights.types_table(s, g, 2023, "v").elstat_status.iloc[0].startswith("unusable")
