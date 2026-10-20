from datetime import date

from traceconomics import htmltext
from traceconomics.sources import elstat, eurostat


def test_elstat_document_links(fixture_bytes):
    docs = elstat.document_links(fixture_bytes("elstat_cpi_page.html"))
    assert len(docs) == 6
    assert ("591429", "Single Integrated Metadata Structure (SIMS v2.0) (January 2026 - )") in docs


def test_elstat_calendar(fixture_bytes):
    dates = elstat.release_dates(fixture_bytes("elstat_calendar.html"))
    assert dates["cpi"][:2] == [date(2026, 1, 13), date(2026, 2, 12)]
    assert dates["hicp"][0] == date(2026, 1, 13)
    assert dates["hbs"] == [date(2026, 9, 25)]


def test_elstat_puf_catalogue(fixture_bytes):
    rows = elstat.puf_rows(fixture_bytes("elstat_puf_catalogue.html"))
    assert "Household Budget Survey (HBS) | 2008 - 2024" in rows
    assert not any(r.upper().startswith("TITLE") for r in rows)


def test_eurostat_last_update(fixture_bytes):
    assert eurostat.last_update(fixture_bytes("eurostat_dataflow_prc_hicp_minr.xml")) == "2026-10-16T23:00:00+0200"


def test_eurostat_calendar(fixture_bytes):
    dates = eurostat.release_dates(fixture_bytes("eurostat_calendar.json"))
    assert dates == [date(2026, 10, 2), date(2026, 10, 16), date(2026, 11, 4), date(2026, 11, 18)]


def test_eurostat_urls():
    assert eurostat.bulk_url("prc_hicp_minr").endswith("/data/PRC_HICP_MINR/?format=TSV&compressed=true")


def test_visible_text_skips_scripts():
    html = b"<html><head><title>x</title></head><body><script>var t=1</script><p>Hello <b>world</b></p></body></html>"
    assert htmltext.visible_text(html) == "Hello world"
