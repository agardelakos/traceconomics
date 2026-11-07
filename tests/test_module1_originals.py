"""ELSTAT's original 2008-2010 CPI tables carried to COICOP 2018, on made-up tables."""

from datetime import UTC, datetime

import pytest

from traceconomics.archive.store import Archive
from traceconomics.checks import FormatError
from traceconomics.module1 import originals
from traceconomics.sources.elstat.original07 import TOTAL, Original07

pytestmark = pytest.mark.unit


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
    """PY-ORIG-001: the 2005-based file is put on the 2009 base

    Given a made-up 2009 original table on the 2005 base
    When it is put on the 2009 base
    Then a class's monthly levels average 100 over 2009
    """
    t = table(2009, "2005", {"0111": (1, [110.0] * 11 + [121.0])})
    levels = originals.on_base_2009({2009: t})[2009]["0111"]
    assert sum(levels.values()) / 12 == pytest.approx(100.0)


def test_a_subclass_takes_its_class_row_else_group_else_division():
    """PY-ORIG-002: a subclass takes its class's row, else its group's, else its division's

    Given a made-up 2010 original table with a class, a group and a division row
    When the row for each COICOP 2018 subclass is chosen
    Then subclasses take their class's, group's or division's row in that order
    """
    t = table(2010, "2009", {"0722": (40, [100.0] * 12), "022": (20, [100.0] * 12), "10": (30, [100.0] * 12)})
    assert originals._row_for("07222", t) == "0722"
    assert originals._row_for("02201", t) == "022"
    assert originals._row_for("10500", t) == "10"


def test_needing_december_2009_a_subclass_takes_a_row_that_has_it():
    """PY-ORIG-004: needing December 2009, a subclass takes only a row that has it

    Given a made-up 2010 original table with a class, a group and a division row
    And earlier levels with a December 2009 for the group only
    When the row for each subclass is chosen where a December 2009 level is needed
    Then the subclass under the group still gets the group's row
    And the subclass whose class, group and division have no December 2009 gets none
    """
    t = table(2010, "2009", {"0722": (40, [100.0] * 12), "022": (20, [100.0] * 12), "10": (30, [100.0] * 12)})
    previous = {"022": {"2009-12": 90.0}}
    assert originals._row_for("02201", t, previous, "2009-12") == "022"
    assert originals._row_for("07222", t, previous, "2009-12") is None    # no December 2009 for 0722 or 072 or 07


def test_old_item_numbers_are_never_matched_to_subclasses():
    # In the old list 07222 is "lubricants" (flat) while the class (car fuels) rose 30%: every v1
    # subclass of 07.2.2, petrol included, must take the class's movement, not the item's.
    """PY-ORIG-003: old item numbers are never matched to subclasses

    Given a made-up 2010 table where old item 07222 (lubricants) is flat while its class (car fuels) rises 30%
    When the table is carried to COICOP 2018
    Then COICOP 2018's 07222 (petrol) follows the class: 130.0 in 2010-06
    And the class keeps its December 2009 level of 100.0
    And 07222 is among the five-digit codes

    In the old list 07222 is "lubricants" (flat) while the class (car fuels) rose 30%: every v1
    subclass of 07.2.2, petrol included, must take the class's movement, not the item's.
    """
    t = table(2010, "2009", {"0722": (40, [130.0] * 12), "07222": (1, [100.0] * 12), "07221": (39, [131.0] * 12)})
    levels = {c: {f"2010-{m:02d}": v[0] for m in range(1, 13)} for c, v in
              (("0722", [130.0]), ("07222", [100.0]), ("07221", [131.0]))}
    prev = {"0722": {"2009-12": 100.0}}
    block, lost = originals.to_2018(t, levels, prev, 2010)
    assert block["07222"]["2010-06"] == pytest.approx(130.0)       # COICOP 2018 07222 (petrol): the class
    assert block["0722"]["2009-12"] == 100.0
    assert "07222" in [c for c in block if len(c) == 5]


def _archive_originals(tmp_path, years):
    archive = Archive(tmp_path)
    for y in years:
        archive.store_bytes("elstat", f"cpi07-original-{y}", f"table {y}".encode(), url=None,
                            retrieved_at=datetime(2026, 10, 1, tzinfo=UTC), ext=".xls")
    return archive


def test_the_three_original_years_become_linked_blocks(tmp_path, monkeypatch):
    """PY-ORIG-005: the archived 2008-2010 original tables become three linked blocks in COICOP 2018

    Given archived original tables for 2008 (2009 base), 2009 (2005 base) and 2010 (2009 base)
    And car fuels (class 07.2.2) flat in 2008 and 2009 and 20% higher through 2010
    When the original blocks are built
    Then each file is read for its own year
    And 2009's block is flat at 100 on December 2008
    And 2010's petrol (07222) is 120 on December 2009, which is 100
    And no subclass under car fuels is left unpriced
    """
    tables = {2008: table(2008, "2009", {"0722": (40, [100.0] * 12)}),
              2009: table(2009, "2005", {"0722": (40, [110.0] * 12)}),
              2010: table(2010, "2009", {"0722": (40, [120.0] * 12)})}
    read = []
    monkeypatch.setattr(originals, "parse", lambda path, year: read.append((path.read_bytes(), year)) or tables[year])
    out, lost = originals.blocks(_archive_originals(tmp_path, originals.YEARS))
    assert read == [(f"table {y}".encode(), y) for y in originals.YEARS]
    assert sorted(out) == [2008, 2009, 2010]
    assert out[2009]["07222"]["2009-06"] == pytest.approx(100.0)
    assert out[2010]["07222"]["2010-06"] == pytest.approx(120.0) and out[2010]["07222"]["2009-12"] == 100.0
    assert not any(code.startswith("0722") for year in lost for code in lost[year])


def test_a_missing_original_year_is_named(tmp_path, monkeypatch):
    """PY-ORIG-006: a missing original table is named

    Given archived original tables for 2008 and 2010 only
    When the original tables are read
    Then a FormatError names the missing 2009 table and its dataset
    """
    monkeypatch.setattr(originals, "parse", lambda path, year: table(year, "2009", {}))
    with pytest.raises(FormatError, match=r"no archived original table 07 for 2009 \(elstat/cpi07-original-2009\)"):
        originals.read(_archive_originals(tmp_path, (2008, 2010)))
