"""Past years of the CPI's table 07, fetched once from ELSTAT's archived month pages.

Table 07 (monthly sub-indices of every CPI item, with that year's weights)
gets a new document ID each year, and only the current year is listed on the
live publication page. Earlier years are listed on the archived page for each
month, e.g. /publication/DKT87/2015-M12. ELSTAT re-issued all years from 2010
in the COICOP 2018 classification with 2020=100, which is the form we need;
each fetched file is checked for that.

This is a one-off, so it is deliberately slow: one request at a time with a
long pause, and nothing already archived is fetched again.
"""

from __future__ import annotations

import re
from pathlib import Path

import xlrd

from traceconomics.sources.base import RunContext
from traceconomics.sources.elstat import BASE, SOURCE, document_links, doc_url, page_content

PAGE_URL = BASE + "/en/statistics/-/publication/DKT87/{year}-M12"


def table07_doc(page: bytes, year: int) -> tuple[str, str] | None:
    """(document ID, title) of the given year's table 07 on an archived month page."""
    pattern = re.compile(rf"^07\.\s.*\(January {year} - December {year}\)")
    for doc, title in document_links(page):
        if pattern.match(title.strip()):
            return doc, title
    return None


# The sheet holding the indices, and how the title names the year, in each language's file.
SHEET_NAMES = ("INDICES", "ΔΕΙΚΤΕΣ")
YEAR_IN_TITLE = ("for {year}", "έτους {year}")


def check_table07(path: Path, year: int) -> list[str]:
    """Problems that mean the file isn't the COICOP 2018, 2020=100 table for that year."""
    try:
        book = xlrd.open_workbook(path, on_demand=True)
        names = [n for n in book.sheet_names() if n.strip() in SHEET_NAMES]
        if not names:
            return [f"no sheet named {' or '.join(SHEET_NAMES)}: {book.sheet_names()}"]
        sheet = book.sheet_by_name(names[0])
    except Exception as exc:  # noqa: BLE001 - any read failure is reported, not raised
        return [f"can't read the file: {exc}"]
    title = " ".join(str(v) for v in sheet.row_values(0))
    header = " ".join(str(v) for v in sheet.row_values(2)).upper()
    problems = []
    if not any(form.format(year=year) in title for form in YEAR_IN_TITLE):
        problems.append(f"title doesn't name {year}: {title.strip()[:120]}")
    if "2020=100" not in title:
        problems.append("title doesn't say 2020=100")
    if "COICOP18" not in header:
        problems.append("header has no COICOP18 column")
    return problems


def fetch_years(ctx: RunContext, years: list[int]) -> list[str]:
    """Archive each year's month page and table 07 (English and Greek). Returns notes for the report."""
    notes = []
    for year in years:
        url = PAGE_URL.format(year=year)
        _, page = ctx.fetch_and_store(SOURCE, f"page-cpi-{year}-M12", url, ext=".html", content_of=page_content)
        if ctx.dry_run or page is None:
            continue
        found = table07_doc(page, year)
        if found is None:
            ctx.failures.append(f"{SOURCE}: no table 07 for {year} on {url}")
            continue
        doc, title = found
        for locale, dataset in (("en", f"doc-{doc}"), ("el", f"doc-{doc}-el")):
            if ctx.archive.latest(SOURCE, dataset):
                notes.append(f"{year} {locale}: {dataset} already archived")
                continue
            res, _ = ctx.fetch_and_store(SOURCE, dataset, doc_url(doc, locale),
                                         extra={"title": title, "listed_on": url})
            if res is None or res.path is None:
                continue
            problems = check_table07(res.path, year) if res.path.suffix == ".xls" else \
                [f"unexpected file type: {res.path.name}"]
            if problems:
                ctx.alerts.append(f"{SOURCE}/{dataset} ({year} {locale}): " + "; ".join(problems))
            else:
                notes.append(f"{year} {locale}: {dataset} stored, checked (COICOP 2018, 2020=100)")
    return notes
