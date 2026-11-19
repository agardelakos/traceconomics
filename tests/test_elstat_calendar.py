"""ELSTAT's release calendar: the page, with its unreadable rows, and the yearly PDFs."""

from datetime import date

import pytest

from traceconomics.checks import FormatError
from traceconomics.sources import elstat
from traceconomics.sources.elstat import calendar_pdf

pytestmark = pytest.mark.unit

# The CPI's and the HICP's release days in 2027, as printed in ELSTAT's 2027 calendar.
DAYS_2027 = [
    date(2027, 1, 13),
    date(2027, 2, 12),
    date(2027, 3, 10),
    date(2027, 4, 9),
    date(2027, 5, 10),
    date(2027, 6, 10),
    date(2027, 7, 9),
    date(2027, 8, 9),
    date(2027, 9, 10),
    date(2027, 10, 8),
    date(2027, 11, 10),
    date(2027, 12, 10),
]


def page(*rows: tuple[str, str]) -> bytes:
    """A calendar page with the given (date as written, indicator) rows, as ELSTAT marks them up."""
    cells = "".join(
        f'<tr><td class="contentDay">{day}</td><td class="contentIndicator">{name}</td>'
        f'<td class="contentPeriod">October 2026</td></tr>'
        for day, name in rows
    )
    return f"<html><body><table>{cells}</table></body></html>".encode()


def monthly_lines(year: int, name: str = "Consumer price index") -> list[str]:
    """Twelve PDF lines, one release a month on the 10th, each for the month before."""
    months = calendar_pdf.MONTHS
    lines = []
    for m in range(1, 13):
        period = f"December {year - 1}" if m == 1 else f"{months[m - 2].title()} {year}"
        lines.append(f"10/{m:02d} {name} {period}")
    return lines


def test_pdf_2027_release_days(fixture_bytes):
    """PY-CAL-001: the 2027 calendar PDF gives every CPI, HICP and HBS release day of 2027

    Given ELSTAT's releases calendar for 2027, as published
    When its release days are read for 2027
    Then the CPI's and the HICP's are the twelve days printed in it, from 2027-01-13 to 2027-12-10
    And the household budget survey's is 2027-09-30
    """
    days = calendar_pdf.release_dates(fixture_bytes("elstat_calendar_2027_en.pdf"), 2027)
    assert days["cpi"] == DAYS_2027
    assert days["hicp"] == DAYS_2027
    assert days["hbs"] == [date(2027, 9, 30)]


def test_pdf_2026_agrees_with_the_page(fixture_bytes):
    """PY-CAL-002: the 2026 calendar PDF and the 2026 calendar page give the same release days

    Given ELSTAT's releases calendar PDF for 2026 and the calendar page as archived on 2026-11-10
    When both are read
    Then their CPI and HBS release days are the same
    And their HICP days are the same except 2026-11-10, whose date the page mistyped as "10/11/2 6"
    """
    pdf = calendar_pdf.release_dates(fixture_bytes("elstat_calendar_2026_en.pdf"), 2026)
    web = elstat.release_dates(fixture_bytes("elstat_calendar_2026-11-10.html"))
    assert pdf["cpi"] == web["cpi"] and len(pdf["cpi"]) == 12
    assert pdf["hbs"] == web["hbs"] == [date(2026, 9, 25)]
    assert set(pdf["hicp"]) - set(web["hicp"]) == {date(2026, 11, 10)}
    assert set(web["hicp"]) <= set(pdf["hicp"])


def test_pdf_2024_older_wording(fixture_bytes):
    """PY-CAL-003: the 2024 calendar PDF, with its older capitalised wording, is read too

    Given ELSTAT's releases calendar for 2024 ("Consumer Price Index", "Harmonised Index of Consumer Prices")
    When its release days are read for 2024
    Then the CPI and the HICP each have twelve, the first on 2024-01-12
    And the household budget survey's is 2024-09-27
    """
    days = calendar_pdf.release_dates(fixture_bytes("elstat_calendar_2024_en.pdf"), 2024)
    assert len(days["cpi"]) == len(days["hicp"]) == 12
    assert days["cpi"][0] == days["hicp"][0] == date(2024, 1, 12)
    assert days["hbs"] == [date(2024, 9, 27)]


def test_pdf_read_for_the_wrong_year_is_refused(fixture_bytes):
    """PY-CAL-004: a calendar PDF read for the wrong year is refused

    Given ELSTAT's releases calendar for 2027
    When its release days are read as if it were 2028's
    Then a format error names CPI rows whose reference month isn't the month before their release
    """
    with pytest.raises(FormatError, match="reference month"):
        calendar_pdf.release_dates(fixture_bytes("elstat_calendar_2027_en.pdf"), 2028)


def test_a_file_that_is_not_a_pdf_is_refused():
    """PY-CAL-005: a file that isn't a PDF is refused

    Given bytes that are an HTML error page, not a PDF
    When they are read as a calendar PDF
    Then a format error says it isn't a readable PDF
    """
    with pytest.raises(FormatError, match="not a readable PDF"):
        calendar_pdf.release_dates(b"<html><body>Service unavailable</body></html>", 2027)


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda lines: lines[:-1], "one CPI release in each month"),
        (lambda lines: [*lines, lines[3]], "one CPI release in each month"),
        (lambda lines: [lines[0].replace("December 2026", "November 2026"), *lines[1:]], "reference month"),
        (lambda lines: [*lines, "31/02 Consumer price index January 2027"], "impossible date"),
    ],
    ids=["a month missing", "a month twice", "wrong reference month", "impossible date"],
)
def test_pdf_rows_that_dont_add_up_are_refused(change, message):
    """PY-CAL-006: calendar PDF rows that don't add up to one release a month are refused

    Given the text lines of a 2027 calendar with one CPI and one HICP release in each month
    When one CPI month is missing, or appears twice, or names the wrong reference month, or a row has an impossible date
    Then a format error says which, instead of release days that may be wrong
    """
    lines = change(monthly_lines(2027)) + monthly_lines(2027, "Harmonised index of consumer prices")
    with pytest.raises(FormatError, match=message):
        calendar_pdf.dates_from_lines(lines, 2027)


def test_pdf_rows_of_other_releases_are_ignored():
    """PY-CAL-007: calendar PDF rows of other releases, and lines that aren't rows, are ignored

    Given a 2027 calendar's text lines for the CPI and the HICP, plus other releases and page text
    When its release days are read
    Then the CPI and the HICP have their twelve days and the HBS none
    """
    lines = ["JANUARY", "M T W T F S S", "13/01 Labour force survey November 2026", *monthly_lines(2027)]
    lines += monthly_lines(2027, "Harmonised index of consumer prices")
    days = calendar_pdf.dates_from_lines(lines, 2027)
    assert [d.month for d in days["cpi"]] == list(range(1, 13)) and len(days["hicp"]) == 12
    assert days["hbs"] == []


def test_page_keeps_unreadable_rows(fixture_bytes):
    """PY-CAL-008: the calendar page's rows with an unreadable date are kept, not dropped

    Given the calendar page as archived on 2026-11-10, whose HICP row for 2026-11-10 has the date "10/11/2 6"
    When the page is read
    Then that row is listed as unreadable, with its date as written and its indicator
    And it is the only one
    """
    cal = elstat.read_calendar(fixture_bytes("elstat_calendar_2026-11-10.html"))
    assert cal.unreadable == [("10/11/2 6", "Harmonized index of consumer prices")]
    assert len(cal.entries) > 300


def test_page_with_four_digit_years(fixture_bytes):
    """PY-CAL-009: a calendar page that writes dates as 4/1/2024 is read

    Given the Wayback Machine's copy of the calendar page of 2024-12-14 (dates like "4/1/2024")
    When its release days are read
    Then no row is unreadable
    And the CPI's first two are 2024-01-12 and 2024-02-15, as in the 2024 PDF
    """
    raw = fixture_bytes("elstat_calendar_2024-12-14.html")
    assert elstat.read_calendar(raw).unreadable == []
    assert elstat.release_dates(raw)["cpi"][:2] == [date(2024, 1, 12), date(2024, 2, 15)]


@pytest.mark.parametrize(
    "written, expected",
    [("13/01/27", date(2027, 1, 13)), ("13/1/2027", date(2027, 1, 13)), ("10/11/2 6", None), ("31/02/27", None)],
    ids=["dd/mm/yy", "d/m/yyyy", "typo", "impossible"],
)
def test_page_date_formats(written, expected):
    """PY-CAL-010: the page's past date formats are read, and anything else is unreadable

    Given a calendar page with one CPI row whose date is written as "13/01/27", "13/1/2027", "10/11/2 6" or "31/02/27"
    When the page's rows are read
    Then the first two give 2027-01-13
    And the typo and the impossible date are listed as unreadable rather than guessed
    """
    raw = page(("13/01/27", "Industrial production index"), (written, "Consumer price index"))
    cal = elstat.read_calendar(raw)
    if expected:
        assert (expected, "Consumer price index", "October 2026") in cal.entries and cal.unreadable == []
    else:
        assert cal.unreadable == [(written, "Consumer price index")]


def test_page_without_readable_rows_is_refused():
    """PY-CAL-011: a calendar page with no readable date is refused

    Given a calendar page whose every row has a date in an unknown format
    When it is read
    Then a format error says no release row has a readable date
    And reading it for change detection still works and gives nothing
    """
    raw = page(("2027-01-13", "Consumer price index"), ("13.02.2027", "Consumer price index"))
    with pytest.raises(FormatError, match="no release row with a readable date"):
        elstat.read_calendar(raw)
    assert elstat.calendar_content(raw) == ""


def test_page_links_the_yearly_pdfs(fixture_bytes):
    """PY-CAL-012: the yearly calendar PDFs are found on the page by their link text

    Given the calendar page as archived on 2026-11-10
    When its calendar PDF links are read
    Then 2027's and 2026's point to their PDFs on statistics.gr, whatever their file names
    And older years ("Press Releases Calendar, 2024") are found too
    """
    links = elstat.calendar_pdf_links(fixture_bytes("elstat_calendar_2026-11-10.html"))
    assert links[2027] == (
        "https://www.statistics.gr/documents/20181/16784295/RELEASES_CALENDAR_2027_EN.pdf/c9f54e57-dae5-33f1-0722-122b00116ff8"
    )
    assert links[2026].startswith("https://www.statistics.gr/documents/") and "CALENDAR_2026" in links[2026]
    assert 2024 in links
