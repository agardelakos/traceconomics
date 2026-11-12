"""Engine tests on small baskets whose answers can be worked out on paper."""

import pytest

from traceconomics.engine import annual_average_rate, annual_rate, chain, monthly_rate, rebase
from traceconomics.engine.chain import link
from traceconomics.engine.tree import ancestors, at_level, leaves

pytestmark = pytest.mark.unit


def flat(value, *periods):
    return {p: value for p in periods}


# -- the tree -----------------------------------------------------------------


def test_ancestors_stop_at_the_division():
    """PY-ENG-001: a code's ancestors stop at the division

    Given a five-digit COICOP code and a division code
    When their ancestors are listed
    Then the subclass lists its class, group and division, nearest first
    And a division has no ancestors (TOTAL is never one)
    """
    assert ancestors("01111") == ["0111", "011", "01"]
    assert ancestors("01") == []


def test_leaves_are_the_finest_weighted_codes():
    """PY-ENG-002: the leaves are the finest codes with a weight

    Given weights at several levels, a zero-weight group and a special aggregate
    When the leaves are taken
    Then only the finest weighted codes remain
    And a parent's uncovered share is left out, not priced with the parent
    And TOTAL and special aggregates are never leaves
    """
    w = {"TOTAL": 1000, "01": 100, "011": 60, "0111": 60, "012": 0, "02": 900, "AP": 5}
    assert leaves(w) == {"0111": 60, "02": 900}  # 01's uncovered 40 is left out, not priced with 01


def test_negative_weight_is_refused():
    """PY-ENG-003: a negative weight is refused

    Given a weight below zero
    When the leaves are taken
    Then a ValueError is raised
    """
    with pytest.raises(ValueError):
        leaves({"01": -1})


def test_at_level():
    """PY-ENG-004: weights at one level of the tree

    Given weights at the division, group and class levels
    When the group level is asked for
    Then only the three-digit codes are returned
    """
    assert at_level({"01": 1, "011": 2, "0111": 3, "TOTAL": 6}, 3) == {"011": 2}


# -- one link ---------------------------------------------------------------


def test_two_item_basket():
    """PY-ENG-005: one link of a two-item basket

    Given 60% food up 10% and 40% clothing flat between December and January
    When the January link is computed
    Then it is 0.6 × 1.10 + 0.4 × 1.00 = 1.06
    """
    # 60% food up 10%, 40% clothing flat: 0.6 * 1.10 + 0.4 * 1.00 = 1.06
    prices = {"01": {"2024-12": 100, "2025-01": 110}, "03": {"2024-12": 100, "2025-01": 100}}
    assert link({"01": 600, "03": 400}, prices, "2025-01", "2024-12") == pytest.approx(1.06)


def test_weights_in_any_unit_are_rescaled():
    """PY-ENG-006: weights in any unit give the same link

    Given the two-item basket with weights 3 and 2 instead of 600 and 400
    When the link is computed
    Then it is still 1.06
    """
    prices = {"01": {"2024-12": 100, "2025-01": 110}, "03": {"2024-12": 100, "2025-01": 100}}
    assert link({"01": 3.0, "03": 2.0}, prices, "2025-01", "2024-12") == pytest.approx(1.06)


def test_prices_on_any_base():
    """PY-ENG-007: price indices on different bases give the same link

    Given food on one base year and clothing on another, with the same movements
    When the link is computed
    Then it is still 1.06: only price ratios matter
    """
    # Only ratios matter: food on 2015=100 and clothing on 2020=100 give the same link.
    prices = {"01": {"2024-12": 150, "2025-01": 165}, "03": {"2024-12": 80, "2025-01": 80}}
    assert link({"01": 600, "03": 400}, prices, "2025-01", "2024-12") == pytest.approx(1.06)


def test_missing_item_index_falls_back_to_its_parent():
    """PY-ENG-008: an item without an index is priced with its parent

    Given a class with two subclasses, one of which has no index
    When the year is chained
    Then the subclass without an index moves with its class
    And the basket counts as fully covered
    And the fallback is reported once, from the subclass to its class
    """
    prices = {
        "0111": {"2024-12": 100, "2025-01": 110},
        "011": {"2024-12": 100, "2025-01": 104},
    }  # 0112 has no index of its own
    result = chain({2025: {"011": 100, "0111": 30, "0112": 70}}, prices, first_year=2025, last_year=2025)
    assert result.links["2025-01"] == pytest.approx(0.3 * 1.10 + 0.7 * 1.04)
    assert result.covered["2025-01"] == 1.0
    assert result.fallback_summary() == {("0112", "011"): 1}


def test_item_with_no_index_anywhere_is_left_out_and_reported():
    """PY-ENG-009: an item with no index anywhere is left out and reported

    Given a basket where one division has no index at any level
    When the year is chained
    Then the link uses the other items alone
    And the coverage drops to their share
    And the item is reported with no index used
    """
    prices = {"01": {"2024-12": 100, "2025-01": 110}}
    result = chain({2025: {"01": 600, "03": 400}}, prices, first_year=2025, last_year=2025)
    assert result.links["2025-01"] == pytest.approx(1.10)
    assert result.covered["2025-01"] == pytest.approx(0.6)
    assert result.fallback_summary() == {("03", None): 1}


def test_all_items_index_is_never_used_as_a_fallback():
    """PY-ENG-010: the all-items index is never a fallback

    Given an item without an index and an all-items index that moved
    When the year is chained
    Then the item is left out rather than priced with the all-items index
    """
    prices = {"TOTAL": {"2024-12": 100, "2025-01": 150}, "01": {"2024-12": 100, "2025-01": 110}}
    result = chain({2025: {"01": 1, "03": 1}}, prices, first_year=2025, last_year=2025)
    assert result.links["2025-01"] == pytest.approx(1.10)


# -- chaining over years --------------------------------------------------------


def test_chaining_with_a_weight_change():
    """PY-ENG-011: chain-linking at December across a weight change

    Given two years with different weights and prices that move in December and January
    When the two years are chained
    Then December 2025 is 112.0 on the old weights
    And January 2026 is linked to December 2025 with the new weights (× 1.075)
    """
    dec24, y25, dec25, jan26 = "2024-12", [f"2025-{m:02d}" for m in range(1, 12)], "2025-12", "2026-01"
    prices = {
        "01": {dec24: 100, **flat(100, *y25), dec25: 120, jan26: 132},
        "03": {dec24: 100, **flat(100, *y25), dec25: 100, jan26: 105},
    }
    weights = {2025: {"01": 600, "03": 400}, 2026: {"01": 500, "03": 500}}
    r = chain(weights, prices, first_year=2025, last_year=2026)
    # December 2025: 0.6 * 1.2 + 0.4 * 1.0 = 1.12 on a base of 100.
    assert r.index["2025-12"] == pytest.approx(112.0)
    # January 2026 is linked to December 2025 with the new weights: 0.5 * 1.10 + 0.5 * 1.05 = 1.075.
    assert r.index["2026-01"] == pytest.approx(112.0 * 1.075)


def test_chain_stops_without_weights_or_december():
    """PY-ENG-012: the chain stops where a December or a year's weights are missing

    Given prices without December 2025
    When two years are chained, then again without the second year's weights
    Then the index ends at November 2025 the first time
    And January 2026 is missing both times
    """
    prices = {"01": {**flat(100, "2024-12", *[f"2025-{m:02d}" for m in range(1, 12)]), "2026-01": 101}}
    r = chain({2025: {"01": 1}, 2026: {"01": 1}}, prices, first_year=2025, last_year=2026)
    assert "2025-11" in r.index and "2025-12" not in r.index and "2026-01" not in r.index
    r = chain({2025: {"01": 1}}, prices, first_year=2025, last_year=2026)
    assert "2026-01" not in r.index


def test_periods_limit_what_is_computed():
    """PY-ENG-013: periods limit what is computed

    Given prices for two months
    When the chain is asked for January only
    Then only January's link is computed
    """
    prices = {"01": flat(100, "2024-12", "2025-01", "2025-02")}
    r = chain({2025: {"01": 1}}, prices, first_year=2025, last_year=2025, periods={"2025-01"})
    assert set(r.links) == {"2025-01"}


# -- rates --------------------------------------------------------------------

INDEX = {**{f"2024-{m:02d}": 100.0 for m in range(1, 13)}, **{f"2025-{m:02d}": 100.0 + m for m in range(1, 13)}}


def test_rates():
    """PY-ENG-014: annual and monthly rates

    Given an index flat at 100 in 2024 that rises by one point a month in 2025
    When the rates are computed
    Then the June annual rate is 6.0%
    And the monthly rate compares with the month before, December for January
    And an annual rate without the year before is missing
    """
    assert annual_rate(INDEX, "2025-06") == pytest.approx(6.0)
    assert monthly_rate(INDEX, "2025-06") == pytest.approx((106 / 105 - 1) * 100)
    assert monthly_rate(INDEX, "2025-01") == pytest.approx(1.0)  # from December 2024
    assert annual_rate(INDEX, "2024-06") is None


def test_annual_average_rate_is_not_the_mean_of_annual_rates():
    """PY-ENG-015: the annual average rate compares yearly averages

    Given two years of monthly index levels
    When the annual average rate is computed
    Then it compares the two years' average levels
    And it is missing without a full year
    And it differs from the mean of the twelve annual rates once the year before isn't flat
    """
    assert annual_average_rate(INDEX, 2025) == pytest.approx(6.5)
    assert annual_average_rate(INDEX, 2026) is None
    # With a falling-then-rising year the two definitions part ways.
    idx = {
        **{f"2024-{m:02d}": 100.0 for m in range(1, 13)},
        **{f"2025-{m:02d}": v for m, v in enumerate([90, 90, 90, 90, 90, 90, 130, 130, 130, 130, 130, 130], 1)},
    }
    mean_of_rates = sum(annual_rate(idx, f"2025-{m:02d}") for m in range(1, 13)) / 12
    assert annual_average_rate(idx, 2025) == pytest.approx(10.0) and mean_of_rates == pytest.approx(10.0)
    idx["2024-01"] = 50.0
    assert annual_average_rate(idx, 2025) != pytest.approx(
        sum(annual_rate(idx, f"2025-{m:02d}") for m in range(1, 13)) / 12
    )


def test_rebase_keeps_rates():
    """PY-ENG-016: rebasing keeps every rate

    Given an index
    When it is rebased to 2025 = 100
    Then 2025 averages 100
    And the annual rates are unchanged
    """
    r = rebase(INDEX, 2025)
    assert sum(r[f"2025-{m:02d}"] for m in range(1, 13)) / 12 == pytest.approx(100.0)
    assert annual_rate(r, "2025-06") == pytest.approx(annual_rate(INDEX, "2025-06"))


# -- per-year prices and the pricing map ------------------------------------------


def test_each_year_links_to_its_own_december():
    """PY-ENG-017: each year links to its own file's December

    Given December 2024 printed on different bases in the 2024 and the 2025 files
    When the years are chained with prices by year
    Then 2025 links to the December of its own file
    And December 2025 is 110, not 55
    """
    # The source prints December 2024 twice: 100 in the 2024 file, 50 in the 2025 file (another base).
    p24 = {"01": {"2023-12": 100, "2024-12": 100}}
    p25 = {"01": {"2024-12": 50, "2025-12": 55}}
    w = {2024: {"01": 1}, 2025: {"01": 1}}
    r = chain(w, {2024: p24, 2025: p25}, first_year=2024, last_year=2025, by_year=True)
    assert r.index["2024-12"] == pytest.approx(100)
    assert r.index["2025-12"] == pytest.approx(110)  # 100 * 55 / 50, not 100 * 55 / 100


def test_price_with_starts_the_search_elsewhere_and_is_reported():
    """PY-ENG-018: the pricing map prices an item with another code

    Given a pricing map that sends one item to its parent and another to a different class
    When the year is chained
    Then each item moves with the index the map names
    And both are reported as fallbacks
    """
    prices = {
        "0111": {"2024-12": 100, "2025-01": 120},
        "01111": {"2024-12": 100, "2025-01": 200},
        "1020": {"2024-12": 100, "2025-01": 105},
    }
    w = {2025: {"01111": 1, "10501": 1}}
    r = chain(w, prices, first_year=2025, last_year=2025, price_with={2025: {"01111": "0111", "10501": "1020"}})
    assert r.links["2025-01"] == pytest.approx((1.2 + 1.05) / 2)  # parent's index, and secondary education's
    assert {(f.code, f.used) for f in r.fallbacks} == {("01111", "0111"), ("10501", "1020")}


def test_drop_takes_an_item_out_and_rescales():
    """PY-ENG-019: the pricing map's drop takes an item out and rescales

    Given an item mapped to drop
    When the year is chained
    Then the item is left out and the rest rescaled, with full coverage
    And without the rule the item would be priced with its parent
    """
    prices = {"01": {"2024-12": 100, "2025-01": 110}, "094": {"2024-12": 100, "2025-01": 200}}
    w = {2025: {"01": 3, "0947": 1}}
    r = chain(w, prices, first_year=2025, last_year=2025, price_with={2025: {"0947": "drop"}})
    assert r.links["2025-01"] == pytest.approx(1.10) and r.covered["2025-01"] == 1.0
    unmapped = chain(w, prices, first_year=2025, last_year=2025)  # without the rule: priced with 094
    assert unmapped.links["2025-01"] == pytest.approx((3 * 1.1 + 2.0) / 4)
