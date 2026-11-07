"""Ribe contributions add up to the annual rate, including across a change of weights."""

import pytest

from traceconomics.engine.rates import annual_rate
from traceconomics.module1 import index
from traceconomics.module1.contributions import ribe
from traceconomics.module1.weights_used import Basket

pytestmark = pytest.mark.unit


def blocks():
    b = {}
    for y in range(2008, 2027):
        food = {f"{y}-{m:02d}": 100 + (m * 2 if y == 2022 else m * 0.3) for m in range(1, 13)}
        b[y] = {"01": {f"{y - 1}-12": 100.0, **food},
                "04": {f"{y - 1}-12": 100.0, **{f"{y}-{m:02d}": 100 + (m * 1.5 if y in (2022, 2023) else 0)
                                                 for m in range(1, 13)}},
                "07": {f"{y - 1}-12": 100.0, **{f"{y}-{m:02d}": 100 - m * 0.2 for m in range(1, 13)}}}
    return b


def baskets():
    out = {}
    for y in range(2008, 2025):
        food = 0.5 if y % 2 else 0.3                  # weights change from year to year
        out[(y, "B", "Q1")] = Basket({"01": food, "04": 0.3, "07": 0.7 - food},
                                     {"01": "normal", "04": "normal", "07": "normal"})
    return out


def test_contributions_add_up_to_the_annual_rate_every_month():
    """PY-CONTRIB-001: Ribe contributions add up to the annual rate every month

    Given made-up prices and B/Q1 baskets whose weights change from year to year
    When the series is built and its Ribe contributions computed
    Then in every month with an annual rate the contributions sum to it, within 1e-9
    And more than 150 months are checked, including 2011-12
    And in 2022-06 food contributes more than transport
    """
    b = blocks()
    s = index.build(None, "B", "Q1", blocks=b, baskets=baskets())
    c = ribe(s, b)
    unrounded = {p: v for p, v in s.chained.index.items()}
    checked = 0
    for period, parts in c.items():
        rate = annual_rate(unrounded, period)
        if rate is None:
            continue
        assert sum(parts.values()) == pytest.approx(rate, abs=1e-9), period
        checked += 1
    # December of the first year comes from equation 8.42a alone (Eurostat's HICP Methodological
    # Manual 2024, section 8.6.3; bibliography key hicp-manual-2024).
    assert checked > 150 and "2011-12" in c
    assert c["2022-06"]["01"] > c["2022-06"]["07"]   # food drives 2022 in this made-up basket
