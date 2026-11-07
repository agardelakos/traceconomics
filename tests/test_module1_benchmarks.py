"""Helpers for rebuilding other studies' settings."""

from traceconomics.module1 import attribution, benchmarks
from traceconomics.module1.weights_used import Basket


def test_kepe_timing_uses_the_same_year_then_two_years_before():
    """PY-BENCH-001: KEPE's timing uses the same year's survey, then the one two years before

    Given index years 2016 to 2025 and surveys 2008 to 2024
    When KEPE's weights timing rule is applied
    Then 2016 and 2017 use their own year's survey
    And from 2022, 2022 uses its own survey and 2023, 2024 and 2025 use the survey two years before
    """
    s = benchmarks.kepe_rule(range(2016, 2026), set(range(2008, 2025)))
    assert [(e.year, e.survey) for e in s][:2] == [(2016, 2016), (2017, 2017)]
    assert [(e.year, e.survey) for e in s if e.year >= 2022] == [(2022, 2022), (2023, 2021), (2024, 2022), (2025, 2023)]


def test_cutting_baskets_to_one_level():
    """PY-BENCH-002: baskets are cut to one level of the tree

    Given a basket with shares at the division, group and subclass levels
    When it is cut to divisions only, and to the group level
    Then the divisions-only basket holds just 01 and 04
    And the group-level basket holds just 011
    """
    b = {(2020, "B", "Q1"): Basket({"01": 0.6, "011": 0.5, "01111": 0.2, "04": 0.4}, {"01": "normal", "04": "normal"})}
    assert benchmarks.divisions_only(b)[(2020, "B", "Q1")].shares == {"01": 0.6, "04": 0.4}
    assert attribution.at_level(b, 3)[(2020, "B", "Q1")].shares == {"011": 0.5}


def test_kepe_figures_are_on_file():
    """PY-BENCH-003: KEPE's published figures are on file

    Given the package's file of KEPE's published figures
    When it is read
    Then chart 1's P20 rate for 2022 is 10.4
    And the text's P20 minus R10 gap for 2022 is 1.9
    """
    pub = benchmarks.kepe_published()
    assert pub["chart1"]["P20"]["2022"] == 10.4 and pub["text"]["P20_minus_R10"]["2022"] == 1.9
