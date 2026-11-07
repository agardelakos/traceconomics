from datetime import date

import pytest

from traceconomics import htmltext
from traceconomics.sources import elstat, eurostat

pytestmark = pytest.mark.unit


def test_elstat_document_links(fixture_bytes):
    """PY-PARSE-001: document links on ELSTAT's CPI page

    Given a saved copy of ELSTAT's CPI page
    When its document links are read
    Then there are 6
    And they include document 591429 with its full title (SIMS v2.0)
    """
    docs = elstat.document_links(fixture_bytes("elstat_cpi_page.html"))
    assert len(docs) == 6
    assert ("591429", "Single Integrated Metadata Structure (SIMS v2.0) (January 2026 - )") in docs


def test_elstat_calendar(fixture_bytes):
    """PY-PARSE-002: release dates on ELSTAT's calendar

    Given a saved copy of ELSTAT's release calendar
    When its release dates are read
    Then the CPI's first two are 2026-01-13 and 2026-02-12
    And the HICP's first is 2026-01-13
    And the HBS has only 2026-09-25
    """
    dates = elstat.release_dates(fixture_bytes("elstat_calendar.html"))
    assert dates["cpi"][:2] == [date(2026, 1, 13), date(2026, 2, 12)]
    assert dates["hicp"][0] == date(2026, 1, 13)
    assert dates["hbs"] == [date(2026, 9, 25)]


def test_elstat_puf_catalogue(fixture_bytes):
    """PY-PARSE-003: rows of ELSTAT's microdata catalogue

    Given a saved copy of ELSTAT's microdata (PUF) catalogue page
    When its rows are read
    Then they include "Household Budget Survey (HBS) | 2008 - 2024"
    And no row is the table's header
    """
    rows = elstat.puf_rows(fixture_bytes("elstat_puf_catalogue.html"))
    assert "Household Budget Survey (HBS) | 2008 - 2024" in rows
    assert not any(r.upper().startswith("TITLE") for r in rows)


def test_eurostat_last_update(fixture_bytes):
    """PY-PARSE-004: a Eurostat dataflow's last update time

    Given a saved Eurostat dataflow for prc_hicp_minr
    When its last update is read
    Then it is "2026-10-16T23:00:00+0200"
    """
    assert eurostat.last_update(fixture_bytes("eurostat_dataflow_prc_hicp_minr.xml")) == "2026-10-16T23:00:00+0200"


def test_eurostat_calendar(fixture_bytes):
    """PY-PARSE-005: release dates on Eurostat's calendar

    Given a saved copy of Eurostat's release calendar
    When its release dates are read
    Then they are 2026-10-02, 2026-10-16, 2026-11-04 and 2026-11-18
    """
    dates = eurostat.release_dates(fixture_bytes("eurostat_calendar.json"))
    assert dates == [date(2026, 10, 2), date(2026, 10, 16), date(2026, 11, 4), date(2026, 11, 18)]


def test_eurostat_urls():
    """PY-PARSE-006: a Eurostat bulk download URL

    Given the dataset code prc_hicp_minr
    When its bulk URL is made
    Then it ends "/data/PRC_HICP_MINR/?format=TSV&compressed=true"
    """
    assert eurostat.bulk_url("prc_hicp_minr").endswith("/data/PRC_HICP_MINR/?format=TSV&compressed=true")


def test_visible_text_skips_scripts():
    """PY-PARSE-007: visible text skips scripts and the title

    Given an HTML page with a title, a script and a paragraph with bold text
    When its visible text is taken
    Then it is "Hello world"
    """
    html = b"<html><head><title>x</title></head><body><script>var t=1</script><p>Hello <b>world</b></p></body></html>"
    assert htmltext.visible_text(html) == "Hello world"
