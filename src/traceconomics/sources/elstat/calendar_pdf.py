"""ELSTAT's yearly release calendar, published as a PDF.

The calendar page on statistics.gr lists the current year only, and switches to the new year
somewhere between mid-December and mid-January. Next year's dates appear first in a PDF
("Releases Calendar, YYYY (pdf)"), linked from the same page months ahead. Read from the PDF,
January's releases are known before they happen.

Each release is one line of the PDF's text: `dd/mm Name Period`, e.g.
`13/01 Consumer price index December 2026`. The year is the calendar's own. Only the CPI, the
HICP and the household budget survey are read. The checks below make the year provable: every
CPI and HICP row names its reference month, which must be the month before its release, so a
PDF read for the wrong year, or read wrongly, fails instead of giving wrong release days.
"""

from __future__ import annotations

import re
from datetime import date
from io import BytesIO

from pypdf import PdfReader

from traceconomics.checks import FormatError, examples, require

ROW = re.compile(r"(\d{2})/(\d{2}) (.+)")
MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]
PERIOD = re.compile(r"(" + "|".join(MONTHS) + r") (\d{4})$")
MONTHLY = ("cpi", "hicp")


def text_lines(pdf: bytes) -> list[str]:
    """Every line of text in the PDF, page after page."""
    try:
        reader = PdfReader(BytesIO(pdf))
        pages = [page.extract_text() or "" for page in reader.pages]
    # pypdf raises many exception types on a damaged or foreign file; each means "can't read it".
    except Exception as exc:  # noqa: BLE001
        raise FormatError(f"not a readable PDF ({type(exc).__name__}: {exc})") from exc
    return [line.strip() for text in pages for line in text.splitlines()]


def release_dates(pdf: bytes, year: int) -> dict[str, list[date]]:
    """Release days per topic (cpi, hicp, hbs) in the calendar PDF for `year`."""
    try:
        lines = text_lines(pdf)
    except FormatError as exc:
        raise FormatError(f"ELSTAT calendar {year} (pdf): {exc}") from exc
    return dates_from_lines(lines, year)


def dates_from_lines(lines: list[str], year: int) -> dict[str, list[date]]:
    """Release days per topic (cpi, hicp, hbs) from the text lines of the calendar PDF for `year`.

    Raises `checks.FormatError` on an impossible date, or unless the CPI and the HICP each have
    one release a month, each for the month before.
    """
    # Imported here: the package's __init__ imports this module.
    from traceconomics.sources.elstat import topic_of

    found: dict[str, list[tuple[date, str]]] = {"cpi": [], "hicp": [], "hbs": []}
    bad_days = []
    for line in lines:
        m = ROW.fullmatch(line)
        if not m:
            continue
        name = " ".join(m[3].split())
        topic = topic_of(name)
        if topic is None:
            continue
        try:
            when = date(year, int(m[2]), int(m[1]))
        except ValueError:
            bad_days.append(line)
            continue
        found[topic].append((when, name))
    require(not bad_days, f"ELSTAT calendar {year} (pdf): rows with an impossible date: {examples(bad_days)}")

    for topic in MONTHLY:
        rows = found[topic]
        # One release a month, each for the month before: twelve rows, January to December.
        months = sorted(when.month for when, _ in rows)
        require(
            months == list(range(1, 13)),
            f"ELSTAT calendar {year} (pdf): expected one {topic.upper()} release in each month, "
            f"found release months {months}",
        )
        wrong = []
        for when, name in rows:
            m = PERIOD.search(name.lower())
            expected = (12, year - 1) if when.month == 1 else (when.month - 1, year)
            if not m or (MONTHS.index(m[1]) + 1, int(m[2])) != expected:
                wrong.append(f"{when:%d/%m} {name}")
        require(
            not wrong,
            f"ELSTAT calendar {year} (pdf): {topic.upper()} rows whose reference month isn't the month "
            f"before their release (the wrong year's file, or misread): {examples(wrong)}",
        )
    return {topic: sorted({when for when, _ in rows}) for topic, rows in found.items()}
