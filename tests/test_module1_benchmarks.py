"""Helpers for rebuilding other studies' settings."""

from traceconomics.module1 import attribution, benchmarks
from traceconomics.module1.weights_used import Basket


def test_kepe_timing_uses_the_same_year_then_two_years_before():
    s = benchmarks.kepe_rule(range(2016, 2026), set(range(2008, 2025)))
    assert [(e.year, e.survey) for e in s][:2] == [(2016, 2016), (2017, 2017)]
    assert [(e.year, e.survey) for e in s if e.year >= 2022] == [(2022, 2022), (2023, 2021), (2024, 2022), (2025, 2023)]


def test_cutting_baskets_to_one_level():
    b = {(2020, "B", "Q1"): Basket({"01": 0.6, "011": 0.5, "01111": 0.2, "04": 0.4}, {"01": "normal", "04": "normal"})}
    assert benchmarks.divisions_only(b)[(2020, "B", "Q1")].shares == {"01": 0.6, "04": 0.4}
    assert attribution.at_level(b, 3)[(2020, "B", "Q1")].shares == {"011": 0.5}


def test_kepe_figures_are_on_file():
    pub = benchmarks.kepe_published()
    assert pub["chart1"]["P20"]["2022"] == 10.4 and pub["text"]["P20_minus_R10"]["2022"] == 1.9
