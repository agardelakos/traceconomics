"""ELSTAT, the Hellenic Statistical Authority (statistics.gr).

Files are served by document ID. Some IDs are overwritten in place every
month (the CPI time-series tables), so a missed release loses that version
for good. Nobody else keeps these files, which is why they come first.

What is fetched:
- the publication pages for the CPI, the HICP and the household budget
  survey, and every document they list;
- the release calendar, to know when to run;
- the catalogue of public use files (microdata), to notice a new survey year.
  The microdata themselves need a login and are added by hand (`traceconomics import`).
"""

from __future__ import annotations

import re
from datetime import date, datetime

from traceconomics import htmltext
from traceconomics.archive.store import Archive
from traceconomics.sources.base import RunContext

SOURCE = "elstat"
BASE = "https://www.statistics.gr"

PAGES = {
    "cpi": f"{BASE}/en/statistics/-/publication/DKT87/-",
    "hicp": f"{BASE}/en/statistics/-/publication/DKT90/-",
    "hbs": f"{BASE}/en/statistics/-/publication/SFA05/-",
}
CALENDAR_URL = f"{BASE}/en/calendar"
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


def calendar_entries(page: bytes) -> list[tuple[date, str, str]]:
    """(release date, indicator, reference period) for each row of the release calendar."""
    out = []
    for row in htmltext.table_rows(page):
        cells = {cls: text for cls, text in row}
        day, name = cells.get("contentDay"), cells.get("contentIndicator")
        if not day or not name:
            continue
        try:
            when = datetime.strptime(day, "%d/%m/%y").date()
        except ValueError:
            continue
        out.append((when, name, cells.get("contentPeriod", "")))
    return out


def release_dates(page: bytes) -> dict[str, list[date]]:
    """Release dates per topic (cpi, hicp, hbs) from the calendar page."""
    out: dict[str, set[date]] = {topic: set() for topic in CALENDAR_TOPICS}
    for when, name, _ in calendar_entries(page):
        for topic, match in CALENDAR_TOPICS.items():
            if match(name.lower()):
                out[topic].add(when)
    return {topic: sorted(days) for topic, days in out.items()}


def calendar_content(page: bytes) -> str:
    return "\n".join(f"{d.isoformat()}\t{n}\t{p}" for d, n, p in calendar_entries(page))


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


def run(ctx: RunContext, state: dict) -> dict[str, list[date]]:
    """Fetch everything due today. Returns the release dates read from the calendar."""
    dates: dict[str, list[date]] = {}

    # 1. The calendar first, so the rest of the run knows what was released.
    result, data = ctx.fetch_and_store(SOURCE, "calendar", CALENDAR_URL, ext=".html",
                                       content_of=calendar_content)
    if data:
        dates = release_dates(data)
        if not any(d > ctx.today for d in dates.get("cpi", [])):
            ctx.alerts.append("ELSTAT calendar: no future CPI release date found. "
                              "Add dates by hand (schedule.extra_release_dates) until it's published.")

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
        ok = True
        for doc, title in docs:
            dataset = f"doc-{doc}"
            if not full and ctx.archive.latest(SOURCE, dataset):
                continue  # already archived, and nothing released since
            res, _ = ctx.fetch_and_store(SOURCE, dataset, DOC_URL.format(doc=doc),
                                         extra={"title": title, "listed_on": url})
            ok = ok and res is not None
        if full and ok:
            last_full[topic] = cutoff.isoformat()

    # 3. The microdata catalogue: a new survey year means a manual download is due.
    result, data = ctx.fetch_and_store(SOURCE, "puf-catalogue", PUF_CATALOGUE_URL, ext=".html",
                                       content_of=lambda b: "\n".join(puf_rows(b)))
    if result and result.status == "stored":
        before = _previous_payload(ctx.archive, "puf-catalogue")
        if before is not None:
            old, new = set(puf_rows(before)), set(puf_rows(data or b""))
            changes = [f"  was: {r}" for r in sorted(old - new)] + [f"  now: {r}" for r in sorted(new - old)]
            ctx.alerts.append("ELSTAT microdata catalogue changed. If a new HBS year is listed, "
                              "download it and run `traceconomics import`:\n" + "\n".join(changes))
    return dates
