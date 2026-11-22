"""The year change, replayed on made-up tables 07: the CPI check passes a correct January and fails
a broken one.

January's release is the one month where three things change at once: every series is linked
again at December, the official basket is reweighted, and items may come and go. An automatic
promote doesn't hold January for a look; instead the build's own CPI check must fail when the
December link or the new basket is wrong. These tests show that it does, on a year change built
the way ELSTAT builds it: each year chained at December of the year before, with that year's
weights.
"""

import importlib
import math

import pytest

from traceconomics.sources.elstat.parse import TOTAL, Table07
from traceconomics.validate import v1_cpi

pytestmark = pytest.mark.integration

# The module, not the function the engine package exports under the same name.
chain = importlib.import_module("traceconomics.engine.chain")

# Shares per mille. In 2026 the basket changes: 03 leaves, 04 comes in, the shares move.
WEIGHTS = {
    2024: {"01": 500.0, "02": 300.0, "03": 200.0},
    2025: {"01": 480.0, "02": 320.0, "03": 200.0},
    2026: {"01": 430.0, "02": 370.0, "04": 200.0},
}
TREND = {"01": 0.004, "02": 0.001, "03": -0.002, "04": 0.009}  # a month


def price(code: str, year: int, month: int) -> float:
    t = (year - 2023) * 12 + month
    return round(100 * math.exp(TREND[code] * t + 0.02 * math.sin(t / 2 + len(code) + int(code))), 3)


def tables(by_year: dict[int, dict[str, float]] = WEIGHTS) -> list[Table07]:
    """Tables 07 for 2024-2026: each year's months and its December link, and the overall index
    chained at December with the year's weights (computed here, not by the engine)."""
    overall = {"2023-12": 100.0}
    out = []
    for year, weights in by_year.items():
        link = f"{year - 1}-12"
        months = [(year - 1, 12)] + [(year, m) for m in range(1, 13)]
        indices = {c: {f"{y}-{m:02d}": price(c, y, m) for y, m in months} for c in weights}
        total = sum(weights.values())
        for y, m in months[1:]:
            p = f"{y}-{m:02d}"
            ratio = sum(w * indices[c][p] / indices[c][link] for c, w in weights.items()) / total
            overall[p] = overall[link] * ratio
        indices[TOTAL] = {p: overall[p] for p in (f"{y}-{m:02d}" for y, m in months)}
        out.append(Table07(year, "en", weights={**weights, TOTAL: 1000.0}, indices=indices))
    return out


def test_a_correct_year_change_passes_the_cpi_check():
    """PY-JAN-001: a correct year change passes the build's CPI check, January included

    Given made-up tables 07 for 2024-2026, the 2026 basket changed (an item out, an item in, shares moved)
    And the overall index chained at December with each year's weights
    When the CPI check (V1-CPI) runs on them
    Then it passes, with every link from 2025-01 to 2026-12 checked
    """
    checked, _, disagreements = v1_cpi.run(tables())
    assert checked.passed, checked.summary()
    assert (checked.first, checked.last, checked.links) == ("2025-01", "2026-12", 24)
    assert disagreements == 0


def test_a_link_at_the_wrong_month_fails_the_cpi_check(monkeypatch):
    """PY-JAN-002: linking at the wrong month fails the build's CPI check from January on

    Given the same made-up tables 07
    When the engine links each year at November instead of December
    Then the CPI check fails
    And its failures include January 2026, the first month of the new basket
    """
    monkeypatch.setattr(chain, "link_month", lambda year: f"{year - 1}-11")
    checked, _, _ = v1_cpi.run(tables())
    assert not checked.passed
    assert any(f.startswith("2026-01:") for f in checked.failures), checked.failures


def test_last_years_basket_kept_fails_the_cpi_check(monkeypatch):
    """PY-JAN-003: keeping last year's basket in the new year fails the build's CPI check in January

    Given the same made-up tables 07
    When 2026 is chained with 2025's weights, as if the switch to the new basket were missed
    Then the CPI check fails
    And its first failure is January 2026
    """
    assemble = v1_cpi.assemble

    def stale(tables):
        weights, prices, official, disagreements = assemble(tables)
        return {**weights, 2026: weights[2025]}, prices, official, disagreements

    monkeypatch.setattr(v1_cpi, "assemble", stale)
    checked, _, _ = v1_cpi.run(tables())
    assert not checked.passed
    assert checked.failures[0].startswith("2026-01:"), checked.failures


def test_last_years_basket_kept_fails_even_when_the_index_cant_show_it(monkeypatch):
    """PY-JAN-004: keeping last year's basket fails the CPI check even when the index can't show it

    Given made-up tables 07 whose 2026 basket differs from 2025's by one per mille moved between two items
    When 2026 is chained with 2025's weights, as if the new basket were missed
    Then January 2026's link to December stays within the check's limit
    And the CPI check still fails, naming 2026 as a year with the same weights as 2025
    """
    close = {**WEIGHTS, 2026: {"01": 479.0, "02": 321.0, "03": 200.0}}
    assemble = v1_cpi.assemble

    def stale(tables):
        weights, prices, official, disagreements = assemble(tables)
        return {**weights, 2026: weights[2025]}, prices, official, disagreements

    monkeypatch.setattr(v1_cpi, "assemble", stale)
    checked, _, _ = v1_cpi.run(tables(close))
    assert not [f for f in checked.failures if "link differs" in f], checked.failures
    assert not checked.passed
    assert checked.failures == ["2026: the weights are the same as 2025's (the new year's basket wasn't read)"]
