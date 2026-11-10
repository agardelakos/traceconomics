"""Groups, spending shares and the per-band V2 check, on small made-up surveys. No real microdata here."""

import pytest

pd = pytest.importorskip("pandas")

from traceconomics.local import v2  # noqa: E402
from traceconomics.local.groups import assign, household_size, quintiles, tenure  # noqa: E402
from traceconomics.local.puf import Survey  # noqa: E402
from traceconomics.local.shares import leaves, shares  # noqa: E402
from traceconomics.sources.elstat.hbs_tables import ALL, Table103  # noqa: E402

pytestmark = pytest.mark.unit

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
    """PY-GROUPS-001: household size on the modified OECD scale

    Given made-up households of one adult; two adults, a 13-year-old and a 3-year-old; and two children with no adult
    When their sizes are worked out
    Then the single adult counts 1 person and 1.0 adult equivalent
    And the second household is 4 persons and 1 + 0.5 + 0.3 + 0.3 equivalents, the 13-year-old counting as a child
    And the household of children is 2 persons and 1.3 equivalents, the first child counting 1
    """
    s = survey([("a", 1, 1, "1", {}), ("b", 1, 1, "1", {}), ("c", 1, 1, "1", {})],
               [("a", 40), ("b", 40), ("b", 38), ("b", 13), ("b", 3), ("c", 12), ("c", 9)])
    size = household_size(s)
    assert size.loc["a"].tolist() == [1, 1.0]
    assert size.loc["b"].tolist() == [4, pytest.approx(1 + 0.5 + 0.3 + 0.3)]   # aged 13 counts as a child
    assert size.loc["c"].tolist() == [2, pytest.approx(1.3)]                    # no adult: the first child counts 1


def test_quintiles_hold_a_fifth_of_the_weight_each():
    """PY-GROUPS-002: each quintile holds a fifth of the weight

    Given ten households of equal weight with values from 10 down to 1
    When they are put in quintiles
    Then the two highest are in quintile 5, the next two in 4, and so on down to 1
    """
    q = quintiles(pd.Series(range(10, 0, -1), dtype=float), pd.Series([1.0] * 10), pd.Series(list("abcdefghij")))
    assert q.tolist() == [5, 5, 4, 4, 3, 3, 2, 2, 1, 1]


def test_quintile_ties_are_broken_by_household_id_and_a_straddler_goes_where_its_middle_is():
    """PY-GROUPS-003: ties are broken by household id and a straddler goes where its middle is

    Given four households, two with the same value, and one with double weight
    When they are put in quintiles
    Then the tied households are ordered by id
    And each household falls in the quintile where the middle of its weight lies (4, 3, 2, 5)
    """
    value = pd.Series([5.0, 5.0, 1.0, 9.0])
    q = quintiles(value, pd.Series([1.0, 1.0, 2.0, 1.0]), pd.Series(["z", "y", "x", "w"]))
    # Order x (weight 2), y, z, w over a total of 5: middles at 0.2, 0.5, 0.7, 0.9.
    assert q.tolist() == [4, 3, 2, 5]


def test_missing_value_or_weight_gets_no_quintile():
    """PY-GROUPS-004: a household with no value or no weight gets no quintile

    Given three households: one complete, one without a value and one with zero weight
    When they are put in quintiles
    Then the complete household, alone, has its middle at 50% and is in quintile 3
    And the other two have no quintile
    """
    q = quintiles(pd.Series([1.0, None, 3.0]), pd.Series([1.0, 1.0, 0.0]), pd.Series(["a", "b", "c"]))
    assert q.iloc[0] == 3 and q.iloc[1:].isna().all()      # alone, the household's middle is at 50%


def test_tenure_renter_first_then_owner_then_housed_free():
    """PY-GROUPS-005: tenure is renter first, then owner, then housed free

    Given households paying rent and imputed rent, imputed rent as owners, imputed rent as housed free, and no rent of any kind
    When their tenure is read
    Then they are renter, owner and rent_free in that order
    And the household with no rent has no tenure
    """
    s = survey([
        ("a", 1, 1, "1", {"0411": 100, "0421": 50}),     # rent and imputed rent: a renter
        ("b", 1, 1, "1", {"0421": 50}),
        ("c", 1, 1, "1", {"04221": 50}),
        ("d", 1, 1, "1", {"0111": 10}),                  # no rent of any kind
    ], adults("abcd"))
    t = tenure(s)
    assert t[:3].tolist() == ["renter", "owner", "rent_free"] and pd.isna(t[3])


def test_unplaceable_households_are_left_out_of_that_grouping_only():
    """PY-GROUPS-006: a household that can't be placed is left out of that grouping only

    Given ten complete households, four of them living mainly on pensions
    And one more with no persons, no rent and no income source
    When the groups are assigned
    Then the odd household is in A's Q1, which needs only income and weight, and in "all"
    And it has no B, C, tenure or pensioners group
    And B's labels are Q1 to Q5 next to the missing one
    And exactly four households are pensioners
    """
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
    """PY-GROUPS-007: the leaves are the finest spending codes

    Given a list of codes from the total down to subclasses
    When the leaves are taken
    Then only the codes with no child in the list remain
    """
    assert leaves(["00", "01", "011", "0111", "04", "042", "0421", "0422", "04221"]) == ["0111", "0421", "04221"]


def test_shares_are_plutocratic_and_add_up():
    """PY-GROUPS-008: spending shares are plutocratic and add up

    Given three made-up households with weights and spending on food, rent, imputed rent and energy
    When the spending shares are computed
    Then for all households, with imputed rent (option 2), food is 1300/4500 and actual plus imputed rent (042) 1400/4500
    And without imputed rent (option 1) food is 1300/3100, and the imputed rent codes are absent
    And in every group and option the leaves sum to 1, and so do the divisions
    And division 04 is the sum of its groups
    """
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
    """PY-GROUPS-009: shares per group count the households that report spending

    Given the three made-up households, one of them pensioners with weight 2
    When the spending shares are computed
    Then the pensioners' rent share is 0.6, from 1 household with weighted count 2
    And among the others, 1 household reports energy and 2 report imputed rent (042)
    And every row is "suppressed", since there are only 3 households
    """
    t = shares(three_households())
    pens = t[(t.grouping == "pensioners") & (t.group == "pensioners") & (t.imputed_rent == 2)].set_index("code")
    assert pens.loc["0411", "share"] == pytest.approx(0.6)
    assert pens.loc["0411", "n_households"] == 1 and pens.loc["0411", "households_weighted"] == 2
    rest = t[(t.grouping == "pensioners") & (t.group == "other") & (t.imputed_rent == 2)].set_index("code")
    assert rest.loc["0451", "n_reporting"] == 1 and rest.loc["042", "n_reporting"] == 2
    assert set(t.reliability) == {"suppressed"}                             # 3 households: all under 20


@pytest.mark.parametrize("n,tier", [(19, "suppressed"), (20, "flagged"), (49, "flagged"), (50, "normal")])
def test_reliability_tiers(n, tier):
    """PY-GROUPS-010: reliability tiers by the number of reporting households

    Given a number of reporting households
    When its reliability tier is read
    Then under 20 is "suppressed", 20 to 49 "flagged" and 50 or more "normal"
    """
    from traceconomics.local.shares import reliability
    assert reliability(n) == tier


# ---- V2 by band -----------------------------------------------------------------------------

def banded_table(year, groups, households, food):
    return Table103(year=year, groups=[ALL] + groups, households=households,
                    purchases={"0111": food}, labels={"0111": "Bread and cereals"})


def test_income_bands_include_their_top_after_rounding_to_the_euro():
    """PY-GROUPS-011: income bands include their top, after rounding to the euro

    Given made-up households with monthly incomes of 500, 750, 750.52 and 2000
    And a published table with bands up to 750, 751-1100 and 1101 and over
    When the households are placed in income bands
    And each band is compared with the table
    Then 500 and 750 are in the first band, 750.52 (rounded to 751) in the second and 2000 in the third
    And each band's food figure matches the table, with one match per band
    """
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


def _size_bands():
    """Made-up households of 1, 2 and 4 members, and a table whose "3 members and over" figure is wrong."""
    s = survey([("a", 1, 1, "1", {"0111": 120}), ("b", 1, 1, "1", {"0111": 240}), ("c", 1, 1, "1", {"0111": 360})],
               [("a", 40), ("b", 40), ("b", 8), ("c", 40), ("c", 39), ("c", 5), ("c", 1)])
    groups = ["1 member", "2 members", "3 members and over"]
    table = banded_table(2013, groups, {ALL: 3, groups[0]: 1, groups[1]: 1, groups[2]: 1},
                         {ALL: 20.0, groups[0]: 10.0, groups[1]: 20.0, groups[2]: 99.0})
    return s, groups, table


def test_households_are_placed_in_size_bands():
    """PY-GROUPS-012: households are placed in size bands

    Given made-up households of 1, 2 and 4 members, and a table with size bands
    When the households are placed in size bands
    Then each household is in its own band: "1 member", "2 members", "3 members and over"
    """
    s, groups, table = _size_bands()
    assert v2.bands(s, table, "size").tolist() == groups


def test_a_wrong_band_figure_fails_that_band_only():
    """PY-GROUPS-026: a wrong band figure fails that band only

    Given made-up households of 1, 2 and 4 members, and a table whose figure for "3 members and over" is wrong
    When the last band is compared with the table, and all households are compared with it
    Then the last band fails with one mismatch: published 99.0 against our 30.0 for 0111
    And the comparison of all households passes
    """
    s, groups, table = _size_bands()
    band = v2.bands(s, table, "size")
    last = v2.compare(s, table, {}, group=groups[2], members=band == groups[2])
    assert not last.passed and last.mismatches == [("0111", "Bread and cereals", 99.0, 30.0)]
    assert v2.compare(s, table, {}).passed


def test_band_count_that_differs_fails():
    """PY-GROUPS-013: a band whose household count differs fails

    Given a table whose household count for the top income band differs from the survey's
    When that band is compared
    Then it fails
    """
    s = survey([("a", 1, 6000, "1", {"0111": 120}), ("b", 1, 24000, "1", {"0111": 120})], adults("ab"))
    groups = ["up 750 €", "751-1100 €", "1101 and over €"]
    table = banded_table(2010, groups, {ALL: 2, groups[0]: 1, groups[1]: 0, groups[2]: 3},
                         {ALL: 10.0, groups[0]: 10.0, groups[2]: 10.0})
    band = v2.bands(s, table, "income")
    assert not v2.compare(s, table, {}, group=groups[2], members=band == groups[2]).passed


def test_uncovered_share_counts_absent_items_whole_and_cut_items_in_part():
    """PY-GROUPS-014: the uncovered share counts absent items whole and cut items in part

    Given a published table with an item absent from the survey and an item cut short in it
    And a list of missing items by year, one listed only for another year
    When the uncovered spending is worked out for the table's year
    Then the absent item counts its whole published figure (2.0) and the cut item the part missing (3.0)
    And the item listed for another year is not counted
    And the uncovered share is 5% of total spending
    """
    s = survey([("a", 1, 1, "1", {"0111": 120}), ("b", 3, 1, "1", {"0111": 240})], adults("ab"))
    s.purchases["07242"] = [12.0, 12.0]                                # tolls, cut: 1 a month in the PUF
    table = Table103(year=2015, groups=[ALL], households={ALL: 4},
                     purchases={"00": {ALL: 100.0}, "0111": {ALL: 17.5}, "12510": {ALL: 2.0}, "07242": {ALL: 4.0}})
    share, gaps = v2.uncovered(s, table, {"12510": [2015], "07242": [2015, 2016], "12610": [2016]})
    assert gaps == {"12510": 2.0, "07242": pytest.approx(3.0)}          # 12610 isn't listed for 2015
    assert share == pytest.approx(0.05)


def test_shares_leave_unplaceable_households_out_of_that_grouping_only():
    """PY-GROUPS-015: shares leave a household that can't be placed out of that grouping only

    Given five complete households and one with no persons and no income source
    When the spending shares are computed without imputed rent
    Then the all-households food share includes it (1400/1650), counting 6 households
    And the B and pensioners groupings count only 5 households
    """
    rows = [(f"h{i}", 1, 1000 * (i + 1), "1", {"0111": 100, "0411": 50}) for i in range(5)]
    rows.append(("odd", 1, 500, "", {"0111": 900}))                  # no persons, no income source
    t = shares(survey(rows, adults(f"h{i}" for i in range(5))))
    food = t[(t.code == "0111") & (t.imputed_rent == 1)].set_index(["grouping", "group"])
    assert food.loc[("all", "all"), "share"] == pytest.approx(1400 / 1650)
    assert food.loc[("all", "all"), "n_households"] == 6
    assert food.xs("B", level="grouping").n_households.sum() == 5
    assert food.xs("pensioners", level="grouping").n_households.sum() == 5


def test_quintile_matrix_matches_one_column_at_a_time():
    """PY-GROUPS-016: the quintile matrix matches quintiles taken one column at a time

    Given values, one of them missing, and two columns of replicate weights
    When quintiles are taken for all columns at once
    Then the household with a missing value is 0 in both columns
    And in each column every household with a quintile has the same one as quintiles taken for that column alone
    """
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
    """PY-GROUPS-017: purchases leave out own production; imputed rent comes from all modes

    Given the three made-up households, one of which grew part of its food, and purchases with no imputed rent
    When shares are computed from purchases and from all modes
    Then without imputed rent food is 1100/2900 from purchases and 1300/3100 from all modes
    And with imputed rent the 042 share adds the survey's imputed rent in either concept: 1400/4300 and 1400/4500
    """
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


def test_deciles_hold_equal_parts_in_order():
    """PY-GROUPS-018: deciles hold equal parts, in order

    Given twenty values of equal weight
    When the values are ranked into ten parts
    Then the deciles hold two values each, in order
    """
    from traceconomics.local.groups import quintile_matrix
    import numpy as np
    q = quintile_matrix(pd.Series(range(20), dtype=float), np.ones(20), pd.Series(range(20)), parts=10)[:, 0]
    assert q.tolist() == [k // 2 + 1 for k in range(20)]


def test_ranking_households_instead_of_persons():
    """PY-GROUPS-027: ranking households instead of persons

    Given ten made-up households, the three poorest with three children each
    When the households' groups are assigned
    Then ranking households puts 2 in Q1 (BH) while ranking persons puts 1 (B)
    And B10 uses only labels D1 to D10, and exactly one household is in BH10's D10
    """
    rows = [(f"h{i}", 1, 1000 * (i + 1), "1", {"0111": 100}) for i in range(10)]
    # Big households at the bottom: ranking people puts fewer households in Q1 than ranking households.
    persons = [(f"h{i}", 40) for i in range(10)] + [(f"h{i}", 10) for i in range(3) for _ in range(3)]
    g = assign(survey(rows, persons))
    assert (g.BH == "Q1").sum() == 2 and (g.B == "Q1").sum() == 1
    assert set(g.B10.dropna()) <= {f"D{k}" for k in range(1, 11)} and (g.BH10 == "D10").sum() == 1


# ---- income limits ---------------------------------------------------------------------------

def test_cut_points_are_midpoints_between_neighbouring_households():
    """PY-GROUPS-019: income limits are midpoints between neighbouring households

    Given ten households of equal weight with values 10 to 100
    When the quintile cut points are taken
    Then they are 25, 45, 65 and 85
    And none is any household's own value
    """
    import numpy as np
    from traceconomics.local.groups import cut_points
    value = pd.Series([float(v) for v in range(10, 110, 10)])            # 10, 20, ... 100, two a fifth
    ids = pd.Series(list("abcdefghij"))
    cuts = cut_points(value, np.ones(10), ids)[:, 0]
    assert cuts.tolist() == [25.0, 45.0, 65.0, 85.0]
    # No limit is any household's own value.
    assert not set(cuts) & set(value)


def test_cut_points_skip_households_without_weight_and_follow_each_column():
    """PY-GROUPS-020: cut points skip households without weight and follow each column

    Given the ten households and two weight columns, the second with one household at zero weight
    When the cut points are taken
    Then the first column gives 25, 45, 65 and 85
    And the second column's first limit moves, and none of its limits is missing
    """
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
    """PY-GROUPS-021: cut points ignore missing values and mark an empty part

    Given three households, one without a value
    When the quintile cut points are taken
    Then at least one limit is missing, since two households can't fill five parts
    """
    import numpy as np
    from traceconomics.local.groups import cut_points
    value = pd.Series([10.0, None, 20.0])
    cuts = cut_points(value, np.ones(3), pd.Series(list("abc")))[:, 0]
    assert np.isnan(cuts).any()       # two households can't fill five parts


def test_limits_table_rounds_midpoints_to_the_euro():
    """PY-GROUPS-022: the limits table rounds the midpoints to the euro

    Given twenty made-up single-adult households with incomes 1000.25 to 20000.25
    When the income limits table is made without replicates
    Then it has limits for Q1 to Q4 in euros per adult equivalent a year
    And the limits are 4500, 8500, 12500 and 16500
    And none has a standard error
    """
    from traceconomics.local.weights import limits_table
    rows = [(f"h{i:02d}", 1, 1000 * (i + 1) + 0.25, "1", {}) for i in range(20)]
    s = survey(rows, adults([r[0] for r in rows]))
    t = limits_table(s, 2015, replicates=0, source_version="test")
    assert t.group.tolist() == ["Q1", "Q2", "Q3", "Q4"] and (t.unit == "EUR_PER_ADULT_EQ_Y").all()
    # Four households a fifth: the limit between the 4th and 5th incomes is (4000.25 + 5000.25) / 2.
    assert t.limit.tolist() == [4500, 8500, 12500, 16500]
    assert t.se.isna().all()          # no replicates asked for


def test_every_household_lies_between_its_fifths_limits():
    """PY-GROUPS-030: every household lies between its fifth's income limits

    Given 300 made-up households of one to five people (some children), with unequal weights and many tied incomes
    When they are placed in fifths of people and the limits between the fifths are taken, before rounding
    Then every household's income per adult equivalent lies between its own fifth's lower and upper limits
    And the limits rise from one fifth to the next
    And some households sit exactly on a limit, so ties are covered
    """
    import numpy as np
    from traceconomics.local.groups import cut_points, ranking
    rng = np.random.default_rng(20261108)
    n = 300
    ids = [f"h{i:03d}" for i in range(n)]
    # Twelve round incomes only, and two households in three alone: equal incomes per adult
    # equivalent come in large blocks, so the cuts fall inside blocks of ties, as with real round
    # reported incomes.
    income = (rng.integers(4, 16, n) * 1000).tolist()
    weight = rng.uniform(50, 900, n).round(3).tolist()
    members = np.where(rng.random(n) < 2 / 3, 1, rng.integers(2, 6, n))
    s = survey([(h, w, inc, "1", {}) for h, w, inc in zip(ids, weight, income)],
               [(h, 40 if k == 0 else int(rng.integers(1, 80)))
                for h, m in zip(ids, members) for k in range(int(m))])
    g = assign(s)
    values, size = ranking(s)
    v = values["B"].to_numpy(float)
    # The same weights as the published limits: people, that is household weight times size.
    cuts = cut_points(values["B"], s.households.weight.to_numpy(float) * size.to_numpy(float), s.households.hh)[:, 0]
    lower = np.concatenate([[-np.inf], cuts])
    upper = np.concatenate([cuts, [np.inf]])
    k = g.B.str[1:].astype(int).to_numpy() - 1
    assert g.B.notna().all()
    outside = ~((v >= lower[k]) & (v <= upper[k]))
    assert not outside.any(), f"{outside.sum()} households outside their fifth's limits"
    assert (np.diff(cuts) > 0).all()
    assert ((v == lower[k]) | (v == upper[k])).any()     # the tie case is exercised


# ---- household types ---------------------------------------------------------------------------

def test_household_types_follow_eurostats_dependent_child_rule():
    """PY-GROUPS-023: household types follow Eurostat's dependent-child rule

    Given made-up households: one adult; a parent and a child under 16; a couple with a 20-year-old student child; the same with the child working; a couple with a student nephew; a couple with a parent and a 25-year-old student child; and a child alone
    When their household types are read
    Then they are A1, A1_DCH, A2_DCH, A_GE3, A_GE3 and A_GE3
    And the household with no adult has no type
    """
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
    """PY-GROUPS-024: household types are a grouping, and households without persons are left out

    Given three made-up households, the last with no person records
    When the groups are assigned
    Then the first two are A1 and A1_DCH under hhtype
    And the third has no household type
    """
    rows = [("a", 1, 1000, "1", {"0111": 10}), ("b", 1, 2000, "1", {"0111": 10}), ("c", 1, 3000, "1", {"0111": 10})]
    g = assign(survey(rows, [("a", 40), ("b", 40), ("b", 5)]))       # c has no person records
    assert g.hhtype.tolist()[:2] == ["A1", "A1_DCH"] and pd.isna(g.hhtype.iloc[2])


def _single_adults(agreeing):
    """Ten made-up single adults; ELSTAT's own type agrees with ours for the first `agreeing`."""
    rows = [(f"h{i}", 1, 1000, "1", {}) for i in range(10)]
    s = survey(rows, adults([r[0] for r in rows]))
    g = assign(s)
    s.households["elstat_type"] = ["1"] * agreeing + ["2"] * (10 - agreeing)
    return s, g


def test_types_table_compares_with_elstats_type():
    """PY-GROUPS-025: the types table compares with ELSTAT's type

    Given ten made-up single adults, with ELSTAT's type agreeing for nine of them
    When the household types table is made for 2015
    Then its A1 row shows "<20" households, a household share of 1.0 and ELSTAT's share of 0.9
    And agreement is 0.9 and every row is "compared"
    """
    from traceconomics.local import weights
    s, g = _single_adults(9)
    t = weights.types_table(s, g, 2015, "v")
    a1 = t.set_index("group").loc["A1"]
    assert a1.n_households == "<20" and a1.share_households == 1.0 and a1.elstat_share_households == 0.9
    assert t.agreement.iloc[0] == 0.9 and (t.elstat_status == "compared").all()


def test_types_table_stops_when_far_from_elstats_type():
    """PY-GROUPS-028: the types table stops when far from ELSTAT's type

    Given ten made-up single adults, with ELSTAT's type agreeing for none of them
    When the household types table is made for 2015
    Then a FormatError says they "agree with ELSTAT's on 0.0%"
    """
    from traceconomics.checks import FormatError
    from traceconomics.local import weights
    s, g = _single_adults(0)
    with pytest.raises(FormatError, match="agree with ELSTAT's on 0.0%"):
        weights.types_table(s, g, 2015, "v")


def test_types_table_marks_elstats_2023_type_unusable():
    """PY-GROUPS-029: in 2023, ELSTAT's type is marked unusable, not compared

    Given ten made-up single adults, with ELSTAT's type agreeing for none of them
    When the household types table is made for 2023
    Then no error is raised, and the ELSTAT status starts with "unusable"

    ELSTAT's own household-type variable is broken in the 2023 survey, so it isn't held against ours.
    """
    from traceconomics.local import weights
    s, g = _single_adults(0)
    assert weights.types_table(s, g, 2023, "v").elstat_status.iloc[0].startswith("unusable")


def test_rent_table_sums_rent_paid_by_tenure():
    """PY-GROUPS-031: the rent table gives rent paid in euros a year, by tenure and for all households

    Given four made-up households: two renters paying 4,800 and 6,000 euros a year with weights 100 and 50, an owner of weight 200 and a household housed free of weight 10, one of the renters with two people
    When the rent table is made for 2015
    Then all households' rent paid is 100 × 4,800 + 50 × 6,000 = 780,000 euros, all of it in the renters' row
    And owners and the housed free pay none
    And the renters are 150 households and 250 people weighted, written "<20" as counted
    """
    from traceconomics.local import weights
    rows = [("r1", 100, 9000, "1", {"0411": 4800}), ("r2", 50, 9000, "1", {"0411": 6000}),
            ("o", 200, 9000, "1", {"0421": 3000}), ("f", 10, 9000, "1", {"04221": 2000})]
    s = survey(rows, [("r1", 40), ("r1", 38), ("r2", 40), ("o", 40), ("f", 40)])
    t = weights.rent_table(s, assign(s), 2015, "v").set_index("tenure")
    assert t.loc["all", "rent_paid_eur"] == 780000.0 and t.loc["renter", "rent_paid_eur"] == 780000.0
    assert t.loc["owner", "rent_paid_eur"] == 0.0 and t.loc["rent_free", "rent_paid_eur"] == 0.0
    assert t.loc["renter", "households_weighted"] == 150.0 and t.loc["renter", "people_weighted"] == 250.0
    assert t.loc["renter", "n_households"] == "<20"


def test_spending_table_lists_household_totals_and_every_figure_compared():
    """PY-GROUPS-032: the spending check table gives each column's household totals, then every figure compared

    Given V2's results for 2014: all households, whose weights add up to fewer households than the table, with a matched item, a differing one and an item the file has no column for
    When the spending check table is made
    Then it starts with the household totals, marked "differs"
    And each item follows with ELSTAT's figure, ours and the result, ours left empty where the file has no column
    """
    from traceconomics.local import weights
    r = v2.V2Result(year=2014, households_puf=4136073.0, households_published=4152372.0, compared=3, matched=1)
    r.rows = [("01111", "Rice", 3.21, 3.2104, "matched"), ("01112", "Bread", 9.5, 9.43, "differs"),
              ("03111", "Clothing materials", 0.09, None, "differs")]
    t = weights.spending_table([r], 2014, "v")
    assert list(t.coicop) == ["households", "01111", "01112", "03111"]
    head = t.iloc[0]
    assert (head.group, head.published, head.ours, head.result) == (ALL, 4152372.0, 4136073.0, "differs")
    assert list(t.result[1:]) == ["matched", "differs", "differs"] and list(t.item[1:]) == ["Rice", "Bread", "Clothing materials"]
    assert t.ours.iloc[3] != t.ours.iloc[3]          # NaN: written as an empty cell
    assert list(t.columns) == weights.SPENDING_COLUMNS
