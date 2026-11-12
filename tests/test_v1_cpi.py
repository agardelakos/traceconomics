"""V1-CPI read from the archive, and its report on the fixed-basket years before 2014."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from traceconomics.archive.store import Archive
from traceconomics.sources.elstat.parse import TOTAL, Table07
from traceconomics.validate import v1_cpi

pytestmark = pytest.mark.integration


def _put(archive, doc, fixture, name, when, fixture_bytes):
    return archive.store_bytes(
        "elstat",
        doc,
        fixture_bytes(fixture),
        url=None,
        ext=Path(fixture).suffix,
        retrieved_at=datetime(*when, tzinfo=UTC),
        extra={"original_name": name},
    )


def test_v1_cpi_reads_the_newest_english_table_of_each_year(tmp_path, fixture_bytes):
    """PY-ELSTAT-007: V1-CPI reads the newest archived English table 07 of each year

    Given an archive holding the 2025 English table 07 twice, retrieved in January and in March under two documents
    And the 2026 English table 07
    And a Greek table 07 and another ELSTAT document
    When V1-CPI is run on the archive
    Then it uses one file per year, 2025 and 2026, the March copy for 2025
    And the Greek table and the other document are not used
    And its check links 2026's nine months to December 2025, with no failures
    """
    archive = Archive(tmp_path)
    en = "A0515_DKT87_TS_MM_01_{y}_12_{y}_07_F_EN{ext}"
    _put(archive, "doc-1", "elstat_cpi07_2025.xls", en.format(y=2025, ext=".xls"), (2026, 1, 15), fixture_bytes)
    _put(archive, "doc-9", "elstat_cpi07_2025.xls", en.format(y=2025, ext=".xls"), (2026, 3, 15), fixture_bytes)
    _put(archive, "doc-2", "elstat_cpi07_2026.xlsx", en.format(y=2026, ext=".xlsx"), (2026, 10, 1), fixture_bytes)
    _put(
        archive,
        "doc-3-el",
        "elstat_cpi07_2011_el.xls",
        "A0515_DKT87_TS_MM_01_2011_12_2011_07_F_GR.xls",
        (2026, 10, 1),
        fixture_bytes,
    )
    _put(archive, "doc-4", "elstat_cpi07_2011_el.xls", "something_else.xls", (2026, 10, 1), fixture_bytes)
    checked, earlier, disagreements, files = v1_cpi.run_archive(archive)
    assert files == {
        2025: archive.root / archive.latest("elstat", "doc-9")["path"],
        2026: archive.root / archive.latest("elstat", "doc-2")["path"],
    }
    assert earlier is None and not checked.failures and checked.links == 9


def _table(year, first_month_value, link=None):
    """A table 07 with one item, the whole basket, rising 1% a month; the overall index equals it."""
    months = {f"{year}-{m:02d}": first_month_value * 1.01 ** (m - 1) for m in range(1, 13)}
    if link is not None:
        months[f"{year - 1}-12"] = link
    return Table07(year, "en", weights={"01": 1000.0, TOTAL: 1000.0}, indices={"01": dict(months), TOTAL: dict(months)})


def test_years_before_2014_are_reported_apart_from_the_strict_check():
    """PY-ELSTAT-008: the fixed-basket years before 2014 are reported apart from the strict check

    Given made-up tables 07 for 2011 to 2014, one item rising 1% a month, the overall index equal to it
    And the 2014 table restating December 2013 0.1% higher than the 2013 table, for the item and the overall index
    When V1-CPI is run on them
    Then the strict check covers 2014 on and passes
    And a separate report covers 2012-2013, named as report only
    And the two restated December values are counted as disagreements
    """
    tables, start = [], 100.0
    for year in (2011, 2012, 2013, 2014):
        dec_before = start / 1.01
        tables.append(_table(year, start, link=dec_before * 1.001 if year == 2014 else None))
        start = start * 1.01**12
    checked, earlier, disagreements = v1_cpi.run(tables)
    assert checked.name == "CPI, finest detail, 2014 on" and not checked.failures, checked.summary()
    assert earlier is not None and earlier.name.startswith("CPI, 2012-2013 (report only")
    assert disagreements == 2
