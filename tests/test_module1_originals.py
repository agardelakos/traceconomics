"""ELSTAT's original 2008-2010 CPI tables carried to COICOP 2018, on made-up tables."""

import pytest

from traceconomics.module1 import originals
from traceconomics.sources.elstat.original07 import TOTAL, Original07


def table(year, base, rows):
    """rows: {code: (weight, 12 monthly values)}."""
    t = Original07(year, base)
    for code, (w, values) in rows.items():
        if w:
            t.weights[code] = w
        t.months[code] = list(values)
        t.average[code] = sum(values) / 12
    t.months[TOTAL] = [100.0] * 12
    t.average[TOTAL] = 100.0
    return t


def test_the_2005_based_file_is_put_on_the_2009_base():
    t = table(2009, "2005", {"0111": (1, [110.0] * 11 + [121.0])})
    levels = originals.on_base_2009({2009: t})[2009]["0111"]
    assert sum(levels.values()) / 12 == pytest.approx(100.0)


def test_a_subclass_takes_its_class_row_else_group_else_division():
    t = table(2010, "2009", {"0722": (40, [100.0] * 12), "022": (20, [100.0] * 12), "10": (30, [100.0] * 12)})
    assert originals._row_for("07222", t) == "0722"
    assert originals._row_for("02201", t) == "022"
    assert originals._row_for("10500", t) == "10"
    previous = {"022": {"2009-12": 90.0}}
    assert originals._row_for("02201", t, previous, "2009-12") == "022"
    assert originals._row_for("07222", t, previous, "2009-12") is None    # no December 2009 for 0722 or 072 or 07


def test_old_item_numbers_are_never_matched_to_subclasses():
    # In the old list 07222 is "lubricants" (flat) while the class (car fuels) rose 30%: every v1
    # subclass of 07.2.2, petrol included, must take the class's movement, not the item's.
    t = table(2010, "2009", {"0722": (40, [130.0] * 12), "07222": (1, [100.0] * 12), "07221": (39, [131.0] * 12)})
    levels = {c: {f"2010-{m:02d}": v[0] for m in range(1, 13)} for c, v in
              (("0722", [130.0]), ("07222", [100.0]), ("07221", [131.0]))}
    prev = {"0722": {"2009-12": 100.0}}
    block, lost = originals.to_2018(t, levels, prev, 2010)
    assert block["07222"]["2010-06"] == pytest.approx(130.0)       # COICOP 2018 07222 (petrol): the class
    assert block["0722"]["2009-12"] == 100.0
    assert "07222" in [c for c in block if len(c) == 5]
