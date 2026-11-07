"""Group indices end to end on made-up prices and baskets."""

import pytest

from traceconomics.checks import FormatError
from traceconomics.module1 import index, output
from traceconomics.module1.weights_used import Basket


def flat_year(y, start, end):
    """A block for year y: December y-1 at `start`, every month of y at `end`."""
    return {f"{y - 1}-12": start, **{f"{y}-{m:02d}": end for m in range(1, 13)}}


def blocks(first=2008, last=2026):
    b = {}
    for y in range(first, last + 1):
        b[y] = {"01": flat_year(y, 100.0, 110.0 if y == 2022 else 100.0),
                "04": flat_year(y, 100.0, 100.0)}
    return b


def baskets(food_q1=0.6, food_q5=0.2):
    out = {}
    for y in range(2008, 2025):                      # surveys 2008-2024, as held today
        for g, f in (("Q1", food_q1), ("Q5", food_q5)):
            out[(y, "B", g)] = Basket({"01": f, "04": 1 - f}, {"01": "normal", "04": "normal"})
    return out


def test_a_price_rise_in_one_item_moves_groups_by_their_share():
    """PY-INDEX-001: a price rise in one item moves each group by its share

    Given made-up prices where food rises 10% through 2022 and nothing else moves
    And baskets for surveys 2008 to 2024 with food at 60% for Q1 and 20% for Q5
    When the B/Q1 and B/Q5 series are built
    Then Q1's annual rate at 2022-12 is about 6.0 and Q5's about 2.0 (within 0.05)
    And Q1's links run from 2009 to 2026
    And 2026's link is a "first" estimate on survey 2023, the newest out on 2026-01-01
    And Q1's index averages 100 over 2025
    """
    b, k = blocks(), baskets()
    q1 = index.build(None, "B", "Q1", blocks=b, baskets=k)
    q5 = index.build(None, "B", "Q5", blocks=b, baskets=k)
    # Food is up 10% through 2022, flat otherwise: Q1 (60% food) about 6%, Q5 (20% food) about 2%.
    assert q1.rates()["2022-12"]["annual"] == pytest.approx(6.0, abs=0.05)
    assert q5.rates()["2022-12"]["annual"] == pytest.approx(2.0, abs=0.05)
    assert q1.schedule[0].year == 2009 and q1.schedule[-1].year == 2026
    # Survey 2025 isn't held: 2026 uses the newest survey out on 2026-01-01 (2023, per the package's dates).
    assert (q1.schedule[-1].status, q1.schedule[-1].survey) == ("first", 2023)
    assert sum(q1.published[f"2025-{m:02d}"] for m in range(1, 13)) / 12 == pytest.approx(100, abs=0.01)


def test_an_item_with_no_index_anywhere_fails_the_run():
    """PY-INDEX-002: an item with no index anywhere fails the run

    Given baskets with an item (05) whose price index stops after 2014
    When the series is built
    Then a FormatError is raised
    """
    b = blocks()
    k = {key: Basket({"01": 0.5, "05": 0.5}, {"01": "normal", "05": "normal"}) for key in baskets()}
    for y in b:                                      # 05 has an index only for price-updating years, not after
        b[y]["05"] = flat_year(y, 100.0, 100.0) if y < 2015 else {}
    with pytest.raises(FormatError):
        index.build(None, "B", "Q1", blocks=b, baskets=k)


def test_gap_rows_use_the_rates_as_shown():
    """PY-INDEX-003: gap rows use the rates as shown

    Given the B/Q1 and B/Q5 series
    When their output rows are made
    Then there is one Q1-Q5 annual-rate gap row for 2022-12, with value text "4.0"
    """
    b, k = blocks(), baskets()
    series = [index.build(None, "B", g, blocks=b, baskets=k) for g in ("Q1", "Q5")]
    gaps = [r for r in output.rows(series)["m1_rates"] if r["unit"] == "RCH_A_GAP" and r["ref_period"] == "2022-12"]
    assert len(gaps) == 1 and gaps[0]["value_text"] == "4.0" and gaps[0]["group"] == "Q1-Q5"


def test_values_resting_on_the_original_tables_are_flagged():
    """PY-INDEX-004: values resting on ELSTAT's original tables are flagged

    Given periods on each side of the end of the original tables
    When the quality flag of each measure is read
    Then the index is "less certain" up to 2010-12, the annual rate up to 2011-12, the monthly rate up to 2011-01 and the annual average for 2011
    And each is unflagged from the next period
    """
    q = output.quality
    assert q("I25", "2010-12") == "less certain" and q("I25", "2011-01") == ""
    assert q("RCH_A", "2011-12") == "less certain" and q("RCH_A", "2012-01") == ""
    assert q("RCH_M", "2011-01") == "less certain" and q("RCH_M", "2011-02") == ""
    assert q("RCH_A_AVG", "2011") == "less certain" and q("RCH_A_AVG", "2012") == ""
