"""ELSTAT CPI table 07 on real files: .xls (English, Greek, without and with a link month) and .xlsx."""

from pathlib import Path

import pytest

from traceconomics.checks import FormatError
from traceconomics.sources.elstat.parse import TOTAL, parse
from traceconomics.validate import v1_cpi

pytestmark = pytest.mark.unit

FIX = Path(__file__).parent / "fixtures"


def test_2025_english_xls():
    """PY-ELSTAT-001: the 2025 English .xls table 07

    Given ELSTAT's CPI table 07 for 2025 in English (.xls)
    When it is parsed
    Then it is read as 2025, English
    And 01111 is labelled "CEREALS", with its weight at full precision
    And the December 2024 column gives 01111's link-month index, and the all-items index has the link month
    And the division weights sum to 1000 within 0.5
    And there is an annual average for all items
    """
    t = parse(FIX / "elstat_cpi07_2025.xls")
    assert (t.year, t.language) == (2025, "en")
    assert t.labels["01111"].strip() == "CEREALS"
    assert t.weights["01111"] == pytest.approx(2.0105415441269416)  # full precision, as in the file
    assert t.indices["01111"]["2024-12"] == pytest.approx(123.76788668518805)  # the DEC-2024 column
    assert "2024-12" in t.indices[TOTAL]  # the link month
    assert abs(sum(w for c, w in t.weights.items() if len(c) == 2) - 1000) < 0.5
    assert TOTAL in t.annual_average


def test_2026_english_xlsx_part_year():
    """PY-ELSTAT-002: the 2026 English .xlsx table 07 for part of a year

    Given ELSTAT's CPI table 07 for 2026 in English (.xlsx), January to September
    When it is parsed
    Then it is read as 2026, English
    And the all-items index has the nine months from 2026-01
    And there is no all-items annual average before December
    """
    t = parse(FIX / "elstat_cpi07_2026.xlsx")
    assert (t.year, t.language) == (2026, "en")
    months = sorted(p for p in t.indices[TOTAL] if p.startswith("2026"))
    assert months[0] == "2026-01" and len(months) == 9  # January to September
    assert TOTAL not in t.annual_average  # no average before December


def test_2011_greek_xls_without_link_month():
    """PY-ELSTAT-003: the 2011 Greek .xls table 07 without a link month

    Given ELSTAT's CPI table 07 for 2011 in Greek (.xls), from the years whose files carry no December column
    When it is parsed
    Then it is read as 2011, Greek
    And the all-items index has twelve months and no December 2010
    And all items are labelled starting "ΓΕΝΙΚΟΣ ΔΕΙΚΤΗΣ"
    And a label containing "ΓΕΝΙΚΑ" ("in general") is kept on its own code, not taken for all items
    """
    t = parse(FIX / "elstat_cpi07_2011_el.xls")
    assert (t.year, t.language) == (2011, "el")
    assert "2010-12" not in t.indices[TOTAL]  # 2010-2013 files carry no December column
    assert len(t.indices[TOTAL]) == 12
    assert t.labels[TOTAL].startswith("ΓΕΝΙΚΟΣ ΔΕΙΚΤΗΣ")
    # Labels containing "ΓΕΝΙΚΑ" ("in general") must not be taken for the overall index.
    assert any("ΓΕΝΙΚΑ" in label for code, label in t.labels.items() if code != TOTAL)


def test_long_rows():
    """PY-ELSTAT-004: the table as long rows

    Given the 2025 table 07
    When it is turned into long rows
    Then they include 01111's annual weight (A, PM, 2025)
    And all items' monthly index for 2025-06 (M, I20)
    """
    t = parse(FIX / "elstat_cpi07_2025.xls")
    rows = list(t.rows())
    assert ("A", "PM", "01111", "2025", t.weights["01111"]) in rows
    assert ("M", "I20", TOTAL, "2025-06", t.indices[TOTAL]["2025-06"]) in rows


def test_not_excel_is_refused(tmp_path):
    """PY-ELSTAT-005: a file that isn't Excel is refused

    Given a CSV file
    When it is parsed as table 07
    Then a FormatError is raised
    """
    f = tmp_path / "x.csv"
    f.write_text("a,b")
    with pytest.raises(FormatError):
        parse(f)


@pytest.mark.integration
def test_v1_cpi_on_2025_and_2026():
    """PY-ELSTAT-006: V1-CPI on the 2025 and 2026 tables

    Given the 2025 and 2026 tables 07
    When V1-CPI is run on them
    Then there are no earlier results and no disagreements
    And the check has no failures
    And 9 links are checked (2026's months linked to December 2025), the worst off by less than 1e-3

    Two files give 2026's links to December 2025, but no annual rates (2025 isn't chained).
    """
    checked, earlier, disagreements = v1_cpi.run(
        [parse(FIX / "elstat_cpi07_2025.xls"), parse(FIX / "elstat_cpi07_2026.xlsx")]
    )
    assert earlier is None and disagreements == 0
    # Two files give 2026's links to December 2025, but no annual rates (2025 isn't chained).
    assert not checked.failures, checked.summary()
    assert checked.links == 9 and checked.worst_link[1] < 1e-3
