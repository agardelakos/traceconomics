"""ELSTAT's original (pre-recode) CPI table VII: the reader, on a committed file of the same layout
and on small made-up sheets for the layouts and refusals no committed file has.

Nothing in the project can write an .xls file, so the made-up sheets stand in for xlrd's sheet."""

from pathlib import Path

import pytest

from traceconomics.checks import FormatError
from traceconomics.sources.elstat import original07
from traceconomics.sources.elstat.original07 import TOTAL, parse

pytestmark = pytest.mark.unit

FIX = Path(__file__).parent / "fixtures"


def test_a_published_table_vii_is_read_item_by_item():
    """PY-ORIG-007: a published Greek table VII is read item by item

    Given ELSTAT's Greek CPI table VII for 2011 (the re-issued file, in the original layout, base 2020)
    When it is read as the 2011 table
    Then the base is "2020" and there are more than 150 rows
    And the overall index is found by its label "ΓΕΝΙΚΟΣ ΔΕΙΚΤΗΣ ΤΙΜΩΝ ΚΑΤΑΝΑΛΩΤΗ", with twelve months and their average
    And each item keeps its weight, its twelve months and its Greek label
    """
    t = parse(FIX / "elstat_cpi07_2011_el.xls", 2011)
    assert t.year == 2011 and t.base == "2020" and len(t.months) > 150
    assert t.labels[TOTAL] == "ΓΕΝΙΚΟΣ ΔΕΙΚΤΗΣ ΤΙΜΩΝ ΚΑΤΑΝΑΛΩΤΗ" and len(t.months[TOTAL]) == 12
    assert t.average[TOTAL] == pytest.approx(sum(t.months[TOTAL]) / 12, abs=0.01)
    assert t.weights["01111"] > 0 and len(t.months["01111"]) == 12
    assert t.labels["01113"] == "ΨΩΜΙ ΚΑΙ ΑΛΛΑ ΠΡΟΪΟΝΤΑ ΑΡΤΟΠΟΙΙΑΣ"


def test_a_table_for_another_year_is_refused():
    """PY-ORIG-008: a table whose title names another year is refused

    Given ELSTAT's Greek CPI table VII for 2011
    When it is read as the 2012 table
    Then a FormatError says the title doesn't name 2012
    """
    with pytest.raises(FormatError, match="the title doesn't name 2012"):
        parse(FIX / "elstat_cpi07_2011_el.xls", 2012)


class Sheet:
    """Stands in for an xlrd sheet: rows of cell values."""

    def __init__(self, rows):
        self.rows = rows
        self.nrows = len(rows)
        self.ncols = max(len(r) for r in rows)

    def cell_value(self, r, c):
        row = self.rows[r]
        return row[c] if c < len(row) else ""


def _item(code, label, weight=1.0, value=100.0):
    return [code, label, weight] + [value] * 12 + [value]


def _sheet(monkeypatch, rows, title="ΠΙΝΑΚΑΣ VII. ΔΤΚ έτους 2009 (Έτος βάσης : 2005=100,0)"):
    sheet = Sheet([[title], [], ["codes"], *rows])

    class Book:
        def sheet_by_index(self, i):
            return sheet
    monkeypatch.setattr(original07.xlrd, "open_workbook", lambda path: Book())


def _items(n):
    return [_item(f"{1000 + k}", f"item {k}") for k in range(n)]


def test_the_layout_rules_of_the_original_files(monkeypatch):
    """PY-ORIG-009: the reader follows the original files' layout

    Given a made-up 2009 table on the 2005 base with 151 items whose codes are stored as numbers
    And the overall index on a row labelled "Γ.Δ.Τ.Κ." with no code and no weight
    And a division heading without numbers and a summary block repeating an item with other values
    When it is read
    Then the base is "2005"
    And codes stored as numbers become text without a decimal point
    And the "Γ.Δ.Τ.Κ." row is the overall index, with no weight
    And the heading is skipped and the repeated item keeps its first values
    """
    rows = [["", "ΔΙΑΤΡΟΦΗ"], _item("", "Γ.Δ.Τ.Κ.", weight="", value=105.0)]
    rows += [_item(float(1000 + k), f"item {k}") for k in range(151)]
    rows += [_item("1000", "item 0 again", value=999.0)]
    _sheet(monkeypatch, rows)
    t = parse(Path("made-up.xls"), 2009)
    assert t.base == "2005"
    assert "1000" in t.months and "1000.0" not in t.months
    assert t.months[TOTAL] == [105.0] * 12 and TOTAL not in t.weights
    assert t.months["1000"] == [100.0] * 12 and t.labels["1000"] == "item 0"


@pytest.mark.parametrize("title, rows, message", [
    ("ΠΙΝΑΚΑΣ VII. ΔΤΚ έτους 2009", _items(151) + [_item("", "ΓΕΝΙΚΟΣ ΔΕΙΚΤΗΣ")], "no base year in the title"),
    ("ΔΤΚ έτους 2009 (2009=100)", _items(151), "no overall index row"),
    ("ΔΤΚ έτους 2009 (2009=100)", _items(10) + [_item("", "ΓΕΝΙΚΟΣ ΔΕΙΚΤΗΣ")], "only 11 rows"),
])
def test_a_file_that_isnt_a_whole_table_is_refused(monkeypatch, title, rows, message):
    """PY-ORIG-010: a file that isn't a whole table VII is refused, never guessed

    Given a made-up 2009 table with no base in its title, or no overall index row, or only 11 rows
    When it is read
    Then a FormatError names what is missing
    """
    _sheet(monkeypatch, rows, title)
    with pytest.raises(FormatError, match=message):
        parse(Path("made-up.xls"), 2009)
