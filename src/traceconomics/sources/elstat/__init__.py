"""ELSTAT, the Hellenic Statistical Authority (statistics.gr).

Files are served by document ID. Some IDs are overwritten in place every
month (the CPI time-series tables), so a missed release loses that version
for good. Nobody else keeps these files, which is why they come first.

What is fetched:
- the publication pages for the CPI, the HICP and the household budget
  survey, and every document they list;
- the release calendar, to know when to run, and its yearly PDF, which carries next
  year's dates before the page switches to the new year (`calendar_pdf.py`);
- the catalogue of public use files (microdata), to notice a new survey year.
  The microdata themselves need a login and are added by hand (`traceconomics import`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from traceconomics import htmltext
from traceconomics.archive.store import Archive
from traceconomics.checks import FormatError, require
from traceconomics.sources.base import RunContext

SOURCE = "elstat"
BASE = "https://www.statistics.gr"

PAGES = {
    "cpi": f"{BASE}/en/statistics/-/publication/DKT87/-",
    "hicp": f"{BASE}/en/statistics/-/publication/DKT90/-",
    "hbs": f"{BASE}/en/statistics/-/publication/SFA05/-",
}
CALENDAR_URL = f"{BASE}/en/calendar"
# The calendar page links one PDF per year. Their file names change every year
# (CALENDAR_2026_ENG.pdf, RELEASES_CALENDAR_2027_EN.pdf), so they are found by the link text.
CALENDAR_PDF_LINK = re.compile(r"(?:Press )?Releases Calendar, (\d{4}) \(pdf\)")
PUF_CATALOGUE_URL = f"{BASE}/spuf-rep/puf_en.jsp"

# The links on the pages carry ":443" and layout parameters; this minimal form works for any ID.
_P = "_documents_WAR_publicationsportlet_INSTANCE_Mr0GiQJSgPHd"
DOC_URL = (
    f"{BASE}/en/statistics?p_p_id=documents_WAR_publicationsportlet_INSTANCE_Mr0GiQJSgPHd"
    f"&p_p_lifecycle=2&{_P}_javax.faces.resource=document&{_P}_ln=downloadResources"
    f"&{_P}_documentID={{doc}}&{_P}_locale=en"
)

DOC_ID = re.compile(r"documentID=(\d+)")


def doc_url(doc: str, locale: str = "en") -> str:
    """Download URL for a document; locale "el" gives the Greek-language file under the same ID."""
    return DOC_URL.format(doc=doc).replace("_locale=en", f"_locale={locale}")


# Calendar entries that trigger a run, matched on the indicator name.
CALENDAR_TOPICS = {
    "cpi": lambda name: "consumer price index" in name and "harmoni" not in name,
    "hicp": lambda name: "harmoni" in name and "consumer price" in name,
    "hbs": lambda name: "household budget survey" in name,
}


def document_links(page: bytes) -> list[tuple[str, str]]:
    """(document ID, title) for every document a publication page lists, in page order."""
    seen: dict[str, str] = {}
    for href, text in htmltext.links(page):
        m = DOC_ID.search(href)
        if m and m.group(1) not in seen:
            seen[m.group(1)] = text
    return list(seen.items())


def page_content(page: bytes) -> str:
    """What counts as a change on a publication page: its documents and their titles."""
    return "\n".join(f"{doc}\t{title}" for doc, title in document_links(page))


def topic_of(name: str) -> str | None:
    """The topic (cpi, hicp, hbs) a calendar row's indicator name belongs to, or None."""
    lowered = name.lower()
    for topic, match in CALENDAR_TOPICS.items():
        if match(lowered):
            return topic
    return None


# The page's date format has changed from year to year (09/01/2023, 4/1/2024, 03/01/25), so a
# day, a month and a two- or four-digit year are all read; anything else is unreadable.
_DAY = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})")


def _day(text: str) -> date | None:
    m = _DAY.fullmatch(text.strip())
    if not m:
        return None
    year = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
    try:
        return date(year, int(m[2]), int(m[1]))
    except ValueError:
        return None


@dataclass(frozen=True)
class CalendarPage:
    """The release calendar page's rows: those with a readable date, and those without one."""

    entries: list[tuple[date, str, str]]  # (release date, indicator, reference period)
    unreadable: list[tuple[str, str]]  # (the date as written, indicator): typos such as "10/11/2 6"


def _calendar_rows(page: bytes) -> CalendarPage:
    entries, unreadable = [], []
    for row in htmltext.table_rows(page):
        cells = {cls: text for cls, text in row}
        day, name = cells.get("contentDay"), cells.get("contentIndicator")
        if not day or not name:
            continue
        when = _day(day)
        if when is None:
            unreadable.append((day, name))
        else:
            entries.append((when, name, cells.get("contentPeriod", "")))
    return CalendarPage(entries, unreadable)


def read_calendar(page: bytes) -> CalendarPage:
    """The calendar page's rows, and the rows whose date can't be read (never dropped silently)."""
    cal = _calendar_rows(page)
    require(
        bool(cal.entries),
        "ELSTAT calendar: no release row with a readable date; the page's layout or date format may have changed",
    )
    return cal


def calendar_entries(page: bytes) -> list[tuple[date, str, str]]:
    """(release date, indicator, reference period) for each row of the release calendar."""
    return read_calendar(page).entries


def _topic_dates(entries: list[tuple[date, str, str]]) -> dict[str, list[date]]:
    out: dict[str, set[date]] = {topic: set() for topic in CALENDAR_TOPICS}
    for when, name, _ in entries:
        topic = topic_of(name)
        if topic:
            out[topic].add(when)
    return {topic: sorted(days) for topic, days in out.items()}


def release_dates(page: bytes) -> dict[str, list[date]]:
    """Release dates per topic (cpi, hicp, hbs) from the calendar page."""
    return _topic_dates(calendar_entries(page))


def calendar_content(page: bytes) -> str:
    """The calendar page's readable rows as text, one per line: what counts as a change of the page."""
    # What counts as a change of the page. Never raises: it runs while the file is being stored.
    return "\n".join(f"{d.isoformat()}\t{n}\t{p}" for d, n, p in _calendar_rows(page).entries)


def calendar_pdf_links(page: bytes) -> dict[int, str]:
    """Year -> URL of each yearly calendar PDF the calendar page links."""
    out = {}
    for href, text in htmltext.links(page):
        m = CALENDAR_PDF_LINK.fullmatch(" ".join(text.split()))
        if m and href.strip():
            out[int(m[1])] = BASE + href.strip() if href.strip().startswith("/") else href.strip()
    return out


@dataclass(frozen=True)
class ReleaseDays:
    """Release days per topic (cpi, hicp, hbs), and the years they cover in full."""

    dates: dict[str, list[date]]  # per topic
    # The years these dates cover in full. For them, the job replaces the future release days it
    # knew with these, so a release that ELSTAT moved doesn't stay behind as a release day.
    years: set[int]


def puf_rows(page: bytes) -> list[str]:
    """The catalogue's rows, e.g. 'Household Budget Survey (HBS) | 2008 - 2024'."""
    rows = []
    for row in htmltext.table_rows(page):
        texts = [t for _, t in row if t]
        if len(texts) >= 2 and texts[0].upper() != "TITLE":
            rows.append(" | ".join(texts))
    return rows


def _previous_payload(archive: Archive, dataset: str) -> bytes | None:
    """The newest stored copy before the one just written."""
    snaps = archive.snapshots(SOURCE, dataset)
    if len(snaps) < 2:
        return None
    return (archive.root / snaps[-2]["path"]).read_bytes()


def _calendar(ctx: RunContext, state: dict) -> ReleaseDays:
    """Release days from the calendar page and, for a year the page doesn't show yet, its PDF."""
    _, data = ctx.fetch_and_store(SOURCE, "calendar", CALENDAR_URL, ext=".html", content_of=calendar_content)
    if not data:
        return ReleaseDays({}, set())
    try:
        cal = read_calendar(data)
    except FormatError as exc:
        ctx.failures.append(f"{SOURCE}/calendar: {exc}")
        return ReleaseDays({}, set())

    others = 0
    for written, name in cal.unreadable:
        if topic_of(name):
            ctx.alerts.append(
                f'ELSTAT calendar: the row "{name}" has a date that can\'t be read ("{written}"), so that '
                "release day isn't known from the page. Check the page; if needed, add the day to "
                "schedule.extra_release_dates."
            )
        else:
            others += 1
    if others:
        ctx.notes.append(f"ELSTAT calendar: {others} row(s) of other releases with a date that can't be read.")

    dates = _topic_dates(cal.entries)
    years = {when.year for when, _, _ in cal.entries}
    for year, pdf_dates in _calendar_pdfs(ctx, state, data).items():
        if year in years:
            # The page wins: ELSTAT says release dates can move after the PDF is out.
            moved = [
                f"{topic.upper()} {when.isoformat()}"
                for topic in CALENDAR_TOPICS
                for when in sorted(set(pdf_dates[topic]) ^ {d for d in dates[topic] if d.year == year})
            ]
            if moved:
                ctx.notes.append(
                    f"ELSTAT calendar {year}: the page and the PDF differ on {', '.join(moved)}; the page's dates are used."
                )
            continue
        for topic in CALENDAR_TOPICS:
            dates[topic] = sorted({*dates[topic], *pdf_dates[topic]})
        years.add(year)

    if not any(d > ctx.today for d in dates["cpi"]):
        ctx.alerts.append(
            "ELSTAT calendar: no future CPI release date found, on the page or in a yearly calendar PDF. "
            "Add dates by hand (schedule.extra_release_dates) until it's published."
        )
    return ReleaseDays(dates, years)


def _calendar_pdfs(ctx: RunContext, state: dict, page: bytes) -> dict[int, dict[str, list[date]]]:
    """This year's and next year's calendar PDFs, where the page links them: their release days.

    A PDF is downloaded once, and again only if its link changes (a new upload gets a new
    address); every run reads the archived copy. So this costs ELSTAT about one request a year.
    The state remembers the address last checked: a re-upload with the same bytes is stored
    once only, so the archive alone would keep the old address and every run would ask again.
    """
    from traceconomics.sources.elstat import calendar_pdf  # needs pypdf; imported where used

    links = calendar_pdf_links(page)
    checked = state.setdefault("elstat_calendar_pdfs", {})
    out = {}
    for year in (ctx.today.year, ctx.today.year + 1):
        url = links.get(year)
        if url is None:
            continue
        dataset = f"calendar-pdf-{year}"
        record = ctx.archive.latest(SOURCE, dataset)
        if record is None or url not in (record.get("url"), checked.get(str(year))):
            result, _ = ctx.fetch_and_store(SOURCE, dataset, url, ext=".pdf")
            if result is not None:
                checked[str(year)] = url
            record = ctx.archive.latest(SOURCE, dataset)
        if record is None:
            continue  # the download failed (reported as a failure) or this is a dry run
        try:
            out[year] = calendar_pdf.release_dates((ctx.archive.root / record["path"]).read_bytes(), year)
        except FormatError as exc:
            ctx.alerts.append(f"{exc}. Its dates are not used; the page's are, when it shows {year}.")
    return out


def new_documents(archive: Archive, http, topic: str) -> list[str]:
    """Document IDs the topic's page lists that the archive doesn't hold.

    One request: the poll's sign that a release is out.

    A changed page is not the sign: the CPI page was archived anew on days without a release
    (2026-11-04, -07, -11, -18), while the release of 2026-11-10 brought IDs never seen before.
    Files ELSTAT updates in place under old IDs come with the full run the sign starts."""
    _, page = http.get_bytes(PAGES[topic], archive.new_tmp())
    docs = document_links(page)
    require(bool(docs), f"ELSTAT page-{topic}: no documents found; the page layout may have changed")
    return [doc for doc, _ in docs if archive.latest(SOURCE, f"doc-{doc}") is None]


def run(ctx: RunContext, state: dict) -> ReleaseDays:
    """Fetch everything due today.

    Returns the release days read from the calendar.
    """
    # 1. The calendar first, so the rest of the run knows what was released.
    days = _calendar(ctx, state)
    dates = days.dates

    # 2. Publication pages and their documents.
    last_full = state.setdefault("elstat_last_full", {})
    for topic, url in PAGES.items():
        result, page = ctx.fetch_and_store(SOURCE, f"page-{topic}", url, ext=".html", content_of=page_content)
        if page is None:
            continue
        docs = document_links(page)
        if not docs:
            ctx.failures.append(f"{SOURCE}/page-{topic}: no documents found; the page layout may have changed")
            continue
        since = last_full.get(topic)
        cutoff = ctx.released_through or ctx.today
        released = [d for d in dates.get(topic, []) if d <= cutoff and (since is None or d > date.fromisoformat(since))]
        full = since is None or bool(released)
        ok, new = True, False
        for doc, title in docs:
            dataset = f"doc-{doc}"
            if not full and ctx.archive.latest(SOURCE, dataset):
                continue  # already archived, and nothing released since
            res, _ = ctx.fetch_and_store(
                SOURCE, dataset, DOC_URL.format(doc=doc), extra={"title": title, "listed_on": url}
            )
            ok = ok and res is not None
            new = new or (res is not None and res.status == "stored")
        if new:
            ctx.brought.add(f"{SOURCE}-{topic}")
        # A release day whose documents all came back unchanged leaves the page unread: the release
        # is late, and ELSTAT updates some files in place under their old IDs (table 05 on
        # 2026-11-10), so the next run must download every document again, not only new IDs.
        if full and ok and (new or not released):
            last_full[topic] = cutoff.isoformat()

    # 3. The microdata catalogue: a new survey year means a manual download is due.
    result, data = ctx.fetch_and_store(
        SOURCE, "puf-catalogue", PUF_CATALOGUE_URL, ext=".html", content_of=lambda b: "\n".join(puf_rows(b))
    )
    if result and result.status == "stored":
        before = _previous_payload(ctx.archive, "puf-catalogue")
        if before is not None:
            old, new = set(puf_rows(before)), set(puf_rows(data or b""))
            changes = [f"  was: {r}" for r in sorted(old - new)] + [f"  now: {r}" for r in sorted(new - old)]
            ctx.alerts.append(
                "ELSTAT microdata catalogue changed. If a new HBS year is listed, "
                "download it and run `traceconomics import`:\n" + "\n".join(changes)
            )
    return days
