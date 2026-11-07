"""CPI blocks, chained price-updating and the weights each year uses, on numbers worked out by hand."""

from datetime import datetime

import duckdb
import pytest

from traceconomics.checks import FormatError
from traceconomics.engine.chain import DROP
from traceconomics.module1.prices import cpi_blocks, update_factor, year_ratio
from traceconomics.module1.schedule import FINAL, FIRST, Entry
from traceconomics.module1.weights_used import Basket, pricing_map, weights_used


def store(rows):
    """An in-memory `observations` table with CPI rows: (archive_dataset, code, period, value)."""
    con = duckdb.connect()
    con.execute("""CREATE TABLE observations (dataset VARCHAR, archive_dataset VARCHAR, key VARCHAR, unit VARCHAR,
                   freq VARCHAR, coicop18 VARCHAR, ref_period VARCHAR, value DOUBLE, status VARCHAR,
                   published_at TIMESTAMP, retrieved_at TIMESTAMP)""")
    t = datetime(2026, 10, 1)
    con.executemany("INSERT INTO observations VALUES ('elstat:cpi07', ?, ?, 'I20', 'M', ?, ?, ?, 'final', ?, ?)",
                    [(f, f"c={c}", c, p, v, t, t) for f, c, p, v in rows])
    return con


def year(file, code, y, value, dec_before=None):
    rows = [(file, code, f"{y}-{m:02d}", value) for m in range(1, 13)]
    if dec_before is not None:
        rows.append((file, code, f"{y - 1}-12", dec_before))
    return rows


def test_each_year_keeps_its_own_december_and_borrows_one_only_when_missing():
    """PY-PRICES-001: each year keeps its own December and borrows one only when missing

    Given CPI table 07 rows for 2012 and 2013 from files with no link month, and 2014 from a file with its own December 2013 on another base
    When the CPI blocks are built
    Then 2013's block borrows December 2012 (100) from the 2012 file
    And 2014's block keeps its own December 2013 (48), not the 2013 file's 110
    And 2012's block has no December 2013
    """
    con = store(year("f2012", "01", 2012, 100) + year("f2013", "01", 2013, 110)       # no link month (old files)
                + year("f2014", "01", 2014, 50, dec_before=48))                         # link month, another base
    b = cpi_blocks(con)
    assert b[2013]["01"]["2012-12"] == 100            # borrowed from the 2012 file
    assert b[2014]["01"]["2013-12"] == 48             # its own copy, not the 2013 file's 110
    assert "2013-12" not in b[2012]["01"]


def test_two_files_for_one_year_are_refused():
    """PY-PRICES-002: two table 07 files for one year are refused

    Given CPI rows for 2014 from two different files
    When the CPI blocks are built
    Then a FormatError about "two table 07 files" is raised
    """
    with pytest.raises(FormatError, match="two table 07 files"):
        cpi_blocks(store(year("a", "01", 2014, 1) + year("b", "01", 2014, 1)))


def blocks_for_updating():
    # 2021: eleven months at 100 and December at 220, so the average is (11*100 + 220)/12 = 110.
    # 2022: December 220 -> 242 (x1.1). 2023: 242 -> 266.2 (x1.1).
    b = {2021: {"01": {**{f"2021-{m:02d}": 100.0 for m in range(1, 12)}, "2021-12": 220.0}}}
    b[2022] = {"01": {"2021-12": 220.0, "2022-12": 242.0}}
    b[2023] = {"01": {"2022-12": 242.0, "2023-12": 266.2}}
    return b


def test_price_update_is_chained_through_each_december():
    """PY-PRICES-003: the price update is chained through each December

    Given blocks where 2021 averages 110 and ends at 220, and 2022 and 2023 each rise 10% December to December
    When a subclass priced through division 01 is updated from survey 2021 to index year 2024
    And the year ratio for 2022 and the update from 2021 to 2022 are taken
    Then the factor is 220/110 × 1.1 × 1.1, priced through 01 at each step
    And the 2022 year ratio is 1.1
    And the update to 2022 (final weights: one year only) is 2.0
    """
    b = blocks_for_updating()
    f, path = update_factor(b, "01111", 2021, 2024)   # priced through its ancestor 01
    assert f == pytest.approx(220 / 110 * 1.1 * 1.1) and path == ["01", "01", "01"]
    assert year_ratio(b, "01", 2022)[0] == pytest.approx(1.1)
    assert update_factor(b, "01", 2021, 2022)[0] == pytest.approx(2.0)   # final weights: one year only


def test_pricing_map_rules():
    """PY-PRICES-004: which index prices each leaf

    Given a basket with games of chance, education not by level, and suppressed food cells
    And a price source with no index for games of chance or education not by level
    When the pricing map is made
    Then games of chance are dropped, 10501 is priced with 1020, and 01111 with 011, its nearest ancestor that isn't suppressed
    And with a source that prices games of chance, they are no longer in the map
    """
    basket = Basket(
        shares={"0947": 0.1, "10501": 0.1, "01": 0.8, "011": 0.8, "0111": 0.8, "01111": 0.5, "01112": 0.3},
        reliability={"0947": "normal", "10501": "suppressed", "01": "normal", "011": "normal",
                     "0111": "suppressed", "01111": "suppressed", "01112": "normal"})
    m = pricing_map(basket, block={"094": {}, "01": {}})
    assert m == {"0947": DROP, "10501": "1020", "01111": "011"}    # 0111 itself is suppressed too: up to 011
    assert "0947" not in pricing_map(basket, block={"0947": {}})   # once the source prices it, it stays


def test_weights_used_drop_and_rescale_after_updating():
    """PY-PRICES-005: weights drop and rescale after price-updating

    Given a basket with food, games of chance and a flat item, and a source with no index for games of chance
    When the 2022 weights are worked out from survey 2021 as final weights
    Then games of chance are dropped with their share of 0.1
    And food's weight is 0.6 × 2 / (0.6 × 2 + 0.3)
    And the weights sum to 1
    """
    b = blocks_for_updating()
    b[2022]["094"] = {"2021-12": 1.0, "2022-12": 1.0}
    basket = Basket({"01": 0.6, "0947": 0.1, "02": 0.3}, {"01": "normal", "0947": "normal", "02": "normal"})
    b[2021]["02"] = {f"2021-{m:02d}": 100.0 for m in range(1, 13)}       # flat: factor 1
    u = weights_used(basket, Entry(2022, 2021, FINAL, "2022-01", "test"), b)
    assert u.dropped == {"0947": 0.1}
    assert u.weights["01"] == pytest.approx(0.6 * 2 / (0.6 * 2 + 0.3))
    assert sum(u.weights.values()) == pytest.approx(1.0)


def test_weights_used_refuses_an_item_it_cannot_update():
    """PY-PRICES-006: an item that can't be price-updated is refused

    Given a basket with an item that has no price index
    When the 2024 weights are worked out from survey 2021
    Then a FormatError saying there is "no index to price-update" is raised
    """
    basket = Basket({"05": 1.0}, {"05": "normal"})
    with pytest.raises(FormatError, match="no index to price-update"):
        weights_used(basket, Entry(2024, 2021, FIRST, "2024-01", "test"), blocks_for_updating())


def test_imputed_rent_is_priced_with_actual_rents_even_when_its_cell_is_small():
    """PY-PRICES-007: imputed rent is priced with actual rents even when its cell is small

    Given a basket whose imputed rent subclasses include a suppressed cell
    When the pricing map is made
    Then both imputed rent classes are priced with actual rents (0411)
    """
    basket = Basket({"04": 0.5, "041": 0.1, "0411": 0.1, "042": 0.4, "0421": 0.35, "0422": 0.05, "01": 0.5},
                    {"04": "normal", "041": "normal", "0411": "normal", "042": "normal", "0421": "normal",
                     "0422": "suppressed", "01": "normal"})
    m = pricing_map(basket, block={"0411": {}, "01": {}})
    assert m == {"0421": "0411", "0422": "0411"}


def test_tutoring_fraction_and_exclusion_with_a_2018_coded_survey():
    """PY-PRICES-008: tutoring's fraction and exclusion with a COICOP 2018 survey

    Given a basket coded in COICOP 2018 with education by level and not by level
    And leaves including 10501
    When the tutoring fraction is taken and tutoring is excluded with no split
    Then the fraction is 10.5's share of 10.1 + 10.2 + 10.5 (0.5)
    And all of 10501 is removed and every other leaf is kept as it was
    """
    from traceconomics.module1.weights_used import exclude_tutoring, tutoring_fraction
    b2024 = Basket({"101": 0.01, "102": 0.02, "105": 0.03}, {})
    assert tutoring_fraction(b2024) == pytest.approx(0.5)
    out, removed = exclude_tutoring({"10101": 0.01, "10200": 0.02, "10501": 0.03, "01": 0.94}, None)
    assert out == {"10101": 0.01, "10200": 0.02, "01": 0.94} and removed == {"10501": 0.03}


def test_tutoring_exclusion_with_an_older_survey_uses_the_groups_split():
    """PY-PRICES-009: tutoring exclusion with an older survey uses the group's split

    Given education leaves totalling 0.10, with a tutoring split of 0.5
    When tutoring is excluded
    And it is excluded again with a split of 0.1
    Then all of 10501 goes and 0.03 more comes from 10.1 and 10.2, 0.05 in all
    And 10.1's and 10.2's leaves shrink in proportion
    And food is untouched
    And with a split of 0.1, 10.5 alone covers it and 10200 keeps 0.04
    """
    from traceconomics.module1.weights_used import exclude_tutoring
    leaves = {"10101": 0.01, "10102": 0.03, "10200": 0.04, "10501": 0.02, "01": 0.90}
    out, removed = exclude_tutoring(leaves, 0.5)
    # Half of 10.1 + 10.2 + 10.5 (0.10) is tutoring: all of 10.5 (0.02), then 0.03 from 0.08 of 10.1-10.2.
    assert "10501" not in out
    assert sum(removed.values()) == pytest.approx(0.05)
    assert out["10200"] == pytest.approx(0.04 * (1 - 0.03 / 0.08))
    assert out["10101"] / out["10102"] == pytest.approx(1 / 3)                 # in proportion
    assert out["01"] == 0.90
    assert exclude_tutoring(leaves, 0.1)[0]["10200"] == 0.04                    # 10.5 alone covers it


def test_tutoring_exclusion_with_a_split_of_one_leaves_zero_not_negative_weights():
    # A group whose 2018-coded survey has all its education in 10.5 (split 1.0) loses all of
    # 10.1-10.2. Computed as 1 - rest / level, the kept share came out about -1e-18 for these
    # shares (rounding), and the engine refuses negative weights.
    """PY-PRICES-010: a tutoring split of 1 leaves zero, not negative, weights

    Given education leaves whose shares round badly, with a tutoring split of 1.0
    When tutoring is excluded
    Then 10101, 10102 and 10200 are exactly 0.0
    And every education leaf's whole share is removed
    And the leaves left for the engine are only food

    A group whose 2018-coded survey has all its education in 10.5 (split 1.0) loses all of
    10.1-10.2. Computed as 1 - rest / level, the kept share came out about -1e-18 for these
    shares (rounding), and the engine refuses negative weights.
    """
    from traceconomics.engine.tree import leaves as tree_leaves
    from traceconomics.module1.weights_used import exclude_tutoring
    leaves = {"10101": 0.01524560164915884, "10102": 4.2121067022213854e-05,
              "10200": 0.008907743881096029, "10501": 0.014430800646815652, "01": 0.9}
    out, removed = exclude_tutoring(leaves, 1.0)
    assert {c: out[c] for c in ("10101", "10102", "10200")} == {"10101": 0.0, "10102": 0.0, "10200": 0.0}
    assert removed == {c: v for c, v in leaves.items() if c != "01"}
    assert tree_leaves(out) == {"01": 0.9}


def test_weights_used_leaves_tutoring_out_only_from_2026():
    """PY-PRICES-011: tutoring is left out only from 2026

    Given a basket with tutoring and the option tutoring "excluded"
    When the weights are worked out for 2025 and for 2026 from same-year surveys
    And for 2026 from survey 2023
    Then 2025 keeps tutoring
    And 2026 drops it (0.1), leaving food at 1.0
    And 2026 from survey 2023 raises a FormatError about the "tutoring split"
    """
    b = blocks_for_updating()
    for y in (2021, 2022, 2023, 2024, 2025, 2026):
        b.setdefault(y, {})
    basket = Basket({"01": 0.9, "10501": 0.1}, {"01": "normal", "10501": "normal"})
    same = Entry(2025, 2025, FINAL, "2025-01", "test")
    assert "10501" in weights_used(basket, same, b, tutoring="excluded").weights        # before 2026
    later = Entry(2026, 2026, FINAL, "2026-01", "test")
    u = weights_used(basket, later, b, tutoring="excluded")
    assert u.weights == {"01": 1.0} and u.dropped == {"10501": 0.1}
    with pytest.raises(FormatError, match="tutoring split"):
        weights_used(basket, Entry(2026, 2023, FIRST, "2026-01", "test"), b, tutoring="excluded")


def _store_with(rows):
    import duckdb
    con = duckdb.connect()
    con.execute("""CREATE TABLE observations (dataset VARCHAR, geo VARCHAR, unit VARCHAR, freq VARCHAR,
                   coicop18 VARCHAR, ref_period VARCHAR, value DOUBLE, key VARCHAR, status VARCHAR,
                   published_at TIMESTAMP, retrieved_at TIMESTAMP)""")
    for code, period, value in rows:
        con.execute("INSERT INTO observations VALUES ('eurostat:prc_hicp_minr', 'GR', 'I25', 'M', ?, ?, ?, ?, 'final',"
                    " TIMESTAMP '2026-10-01', TIMESTAMP '2026-10-01')", [code, period, value, code])
    return con


def test_hicp_blocks_keep_an_item_only_for_years_it_fully_prices():
    """PY-PRICES-012: HICP blocks keep an item only for years it fully prices

    Given HICP rows for food over 2014-2015, an item that stops in 2014-12 and one that starts in 2015-12
    When the HICP blocks are built
    Then the item that stops is in 2014's block but not 2015's
    And the item that starts in a December is not in 2015's block
    And food's 2015 block holds December 2014 and the twelve months of 2015
    """
    from traceconomics.module1.prices import hicp_blocks
    rows = [("01", f"{y}-{m:02d}", 100.0) for y in (2014, 2015) for m in range(1, 13)] + [("01", "2013-12", 99.0)]
    rows += [("105", f"2014-{m:02d}", 100.0) for m in range(1, 13)] + [("105", "2013-12", 99.0)]   # stops 2014-12
    rows += [("0947", "2015-12", 100.0)]                                                            # starts in a December
    b = hicp_blocks(_store_with(rows))
    assert "105" in b[2014] and "105" not in b[2015]
    assert "0947" not in b[2015]
    assert sorted(b[2015]["01"]) == ["2014-12"] + [f"2015-{m:02d}" for m in range(1, 13)]
