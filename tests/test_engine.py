"""Engine tests on small baskets whose answers can be worked out on paper."""

import pytest

from traceconomics.engine import annual_average_rate, annual_rate, chain, monthly_rate, rebase
from traceconomics.engine.chain import link
from traceconomics.engine.tree import ancestors, at_level, leaves


def flat(value, *periods):
    return {p: value for p in periods}


# -- the tree -----------------------------------------------------------------

def test_ancestors_stop_at_the_division():
    assert ancestors("01111") == ["0111", "011", "01"]
    assert ancestors("01") == []


def test_leaves_are_the_finest_weighted_codes():
    w = {"TOTAL": 1000, "01": 100, "011": 60, "0111": 60, "012": 0, "02": 900, "AP": 5}
    assert leaves(w) == {"0111": 60, "02": 900}  # 01's uncovered 40 is left out, not priced with 01


def test_negative_weight_is_refused():
    with pytest.raises(ValueError):
        leaves({"01": -1})


def test_at_level():
    assert at_level({"01": 1, "011": 2, "0111": 3, "TOTAL": 6}, 3) == {"011": 2}


# -- one link ---------------------------------------------------------------

def test_two_item_basket():
    # 60% food up 10%, 40% clothing flat: 0.6 * 1.10 + 0.4 * 1.00 = 1.06
    prices = {"01": {"2024-12": 100, "2025-01": 110}, "03": {"2024-12": 100, "2025-01": 100}}
    assert link({"01": 600, "03": 400}, prices, "2025-01", "2024-12") == pytest.approx(1.06)


def test_weights_in_any_unit_are_rescaled():
    prices = {"01": {"2024-12": 100, "2025-01": 110}, "03": {"2024-12": 100, "2025-01": 100}}
    assert link({"01": 3.0, "03": 2.0}, prices, "2025-01", "2024-12") == pytest.approx(1.06)


def test_prices_on_any_base():
    # Only ratios matter: food on 2015=100 and clothing on 2020=100 give the same link.
    prices = {"01": {"2024-12": 150, "2025-01": 165}, "03": {"2024-12": 80, "2025-01": 80}}
    assert link({"01": 600, "03": 400}, prices, "2025-01", "2024-12") == pytest.approx(1.06)


def test_missing_item_index_falls_back_to_its_parent():
    prices = {"0111": {"2024-12": 100, "2025-01": 110},
              "011": {"2024-12": 100, "2025-01": 104}}  # 0112 has no index of its own
    result = chain({2025: {"011": 100, "0111": 30, "0112": 70}}, prices, first_year=2025, last_year=2025)
    assert result.links["2025-01"] == pytest.approx(0.3 * 1.10 + 0.7 * 1.04)
    assert result.covered["2025-01"] == 1.0
    assert result.fallback_summary() == {("0112", "011"): 1}


def test_item_with_no_index_anywhere_is_left_out_and_reported():
    prices = {"01": {"2024-12": 100, "2025-01": 110}}
    result = chain({2025: {"01": 600, "03": 400}}, prices, first_year=2025, last_year=2025)
    assert result.links["2025-01"] == pytest.approx(1.10)
    assert result.covered["2025-01"] == pytest.approx(0.6)
    assert result.fallback_summary() == {("03", None): 1}


def test_all_items_index_is_never_used_as_a_fallback():
    prices = {"TOTAL": {"2024-12": 100, "2025-01": 150}, "01": {"2024-12": 100, "2025-01": 110}}
    result = chain({2025: {"01": 1, "03": 1}}, prices, first_year=2025, last_year=2025)
    assert result.links["2025-01"] == pytest.approx(1.10)


# -- chaining over years --------------------------------------------------------

def test_chaining_with_a_weight_change():
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
    prices = {"01": {**flat(100, "2024-12", *[f"2025-{m:02d}" for m in range(1, 12)]), "2026-01": 101}}
    r = chain({2025: {"01": 1}, 2026: {"01": 1}}, prices, first_year=2025, last_year=2026)
    assert "2025-11" in r.index and "2025-12" not in r.index and "2026-01" not in r.index
    r = chain({2025: {"01": 1}}, prices, first_year=2025, last_year=2026)
    assert "2026-01" not in r.index


def test_periods_limit_what_is_computed():
    prices = {"01": flat(100, "2024-12", "2025-01", "2025-02")}
    r = chain({2025: {"01": 1}}, prices, first_year=2025, last_year=2025, periods={"2025-01"})
    assert set(r.links) == {"2025-01"}


# -- rates --------------------------------------------------------------------

INDEX = {**{f"2024-{m:02d}": 100.0 for m in range(1, 13)},
         **{f"2025-{m:02d}": 100.0 + m for m in range(1, 13)}}


def test_rates():
    assert annual_rate(INDEX, "2025-06") == pytest.approx(6.0)
    assert monthly_rate(INDEX, "2025-06") == pytest.approx((106 / 105 - 1) * 100)
    assert monthly_rate(INDEX, "2025-01") == pytest.approx(1.0)  # from December 2024
    assert annual_rate(INDEX, "2024-06") is None


def test_annual_average_rate_is_not_the_mean_of_annual_rates():
    assert annual_average_rate(INDEX, 2025) == pytest.approx(6.5)
    assert annual_average_rate(INDEX, 2026) is None
    # With a falling-then-rising year the two definitions part ways.
    idx = {**{f"2024-{m:02d}": 100.0 for m in range(1, 13)},
           **{f"2025-{m:02d}": v for m, v in enumerate([90, 90, 90, 90, 90, 90, 130, 130, 130, 130, 130, 130], 1)}}
    mean_of_rates = sum(annual_rate(idx, f"2025-{m:02d}") for m in range(1, 13)) / 12
    assert annual_average_rate(idx, 2025) == pytest.approx(10.0) and mean_of_rates == pytest.approx(10.0)
    idx["2024-01"] = 50.0
    assert annual_average_rate(idx, 2025) != pytest.approx(
        sum(annual_rate(idx, f"2025-{m:02d}") for m in range(1, 13)) / 12)


def test_rebase_keeps_rates():
    r = rebase(INDEX, 2025)
    assert sum(r[f"2025-{m:02d}"] for m in range(1, 13)) / 12 == pytest.approx(100.0)
    assert annual_rate(r, "2025-06") == pytest.approx(annual_rate(INDEX, "2025-06"))


# -- per-year prices and the pricing map ------------------------------------------

def test_each_year_links_to_its_own_december():
    # The source prints December 2024 twice: 100 in the 2024 file, 50 in the 2025 file (another base).
    p24 = {"01": {"2023-12": 100, "2024-12": 100}}
    p25 = {"01": {"2024-12": 50, "2025-12": 55}}
    w = {2024: {"01": 1}, 2025: {"01": 1}}
    r = chain(w, {2024: p24, 2025: p25}, first_year=2024, last_year=2025, by_year=True)
    assert r.index["2024-12"] == pytest.approx(100)
    assert r.index["2025-12"] == pytest.approx(110)      # 100 * 55 / 50, not 100 * 55 / 100


def test_price_with_starts_the_search_elsewhere_and_is_reported():
    prices = {"0111": {"2024-12": 100, "2025-01": 120}, "01111": {"2024-12": 100, "2025-01": 200},
              "1020": {"2024-12": 100, "2025-01": 105}}
    w = {2025: {"01111": 1, "10501": 1}}
    r = chain(w, prices, first_year=2025, last_year=2025,
              price_with={2025: {"01111": "0111", "10501": "1020"}})
    assert r.links["2025-01"] == pytest.approx((1.2 + 1.05) / 2)   # parent's index, and secondary education's
    assert {(f.code, f.used) for f in r.fallbacks} == {("01111", "0111"), ("10501", "1020")}


def test_drop_takes_an_item_out_and_rescales():
    prices = {"01": {"2024-12": 100, "2025-01": 110}, "094": {"2024-12": 100, "2025-01": 200}}
    w = {2025: {"01": 3, "0947": 1}}
    r = chain(w, prices, first_year=2025, last_year=2025, price_with={2025: {"0947": "drop"}})
    assert r.links["2025-01"] == pytest.approx(1.10) and r.covered["2025-01"] == 1.0
    unmapped = chain(w, prices, first_year=2025, last_year=2025)      # without the rule: priced with 094
    assert unmapped.links["2025-01"] == pytest.approx((3 * 1.1 + 2.0) / 4)
