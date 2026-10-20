"""Eurostat HICP datasets, all countries.

Each live dataset is downloaded in full (one compressed TSV file) only when
Eurostat's "last data update" time has changed since our last copy. Eurostat
keeps flash and first-final values itself (prc_hicp_fpd), so our copies mainly
add later revisions. The ECOICOP v1 datasets are frozen since 2025-12 and are
copied once, in case they are removed.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from urllib.parse import quote

from traceconomics import htmltext
from traceconomics.sources.base import FetchError, RunContext

SOURCE = "eurostat"
API = "https://ec.europa.eu/eurostat/api/dissemination"

LIVE = ("prc_hicp_minr", "prc_hicp_iw", "prc_hicp_fpd")
FROZEN = ("prc_hicp_midx", "prc_hicp_inw", "prc_hicp_fp")
METADATA = {"esms-prc_hicp": "https://ec.europa.eu/eurostat/cache/metadata/en/prc_hicp_esms.htm"}

CALENDAR_URL = (
    "https://ec.europa.eu/eurostat/o/calendars/eventsJson?theme=0&category=0&keywords="
    "&isEuroindicator=true&authorInclude=&authorExclude=&start={start}&end={end}"
)

UPDATE_DATA = re.compile(
    r"<c:AnnotationTitle>([^<]+)</c:AnnotationTitle>\s*<c:AnnotationType>UPDATE_DATA</c:AnnotationType>"
)


def bulk_url(dataset: str) -> str:
    return f"{API}/sdmx/2.1/data/{dataset.upper()}/?format=TSV&compressed=true"


def dataflow_url(dataset: str) -> str:
    return f"{API}/sdmx/2.1/dataflow/ESTAT/{dataset.upper()}/latest"


def last_update(dataflow_xml: bytes) -> str | None:
    """Eurostat's "last data update" time from a dataflow description."""
    m = UPDATE_DATA.search(dataflow_xml.decode("utf-8", "replace"))
    return m.group(1).strip() if m else None


def calendar_url(today: date) -> str:
    def stamp(d: date) -> str:
        return quote(f"{d.isoformat()}T00:00:00+01:00", safe=":")

    return CALENDAR_URL.format(start=stamp(today - timedelta(days=45)), end=stamp(today + timedelta(days=400)))


def release_dates(calendar_json: bytes) -> list[date]:
    """Days with an HICP release (flash or full), from Eurostat's release calendar."""
    events = json.loads(calendar_json)
    days = set()
    for e in events:
        if "inflation" in e.get("title", "").lower():
            # "start" looks like UTC ("11:00Z") but is really 11:00 Brussels time; the date is what matters.
            days.add(datetime.fromisoformat(e["start"][:10]).date())
    return sorted(days)


def calendar_content(calendar_json: bytes) -> str:
    events = json.loads(calendar_json)
    keep = sorted((e.get("start", ""), e.get("title", ""), e.get("period", "")) for e in events)
    return "\n".join("\t".join(k) for k in keep)


def run(ctx: RunContext, state: dict) -> list[date]:
    """Fetch what changed. Returns HICP release dates from the calendar."""
    dates: list[date] = []
    _, data = ctx.fetch_and_store(SOURCE, "calendar", calendar_url(ctx.today), ext=".json",
                                  content_of=calendar_content)
    if data:
        try:
            dates = release_dates(data)
        except (ValueError, KeyError) as exc:
            ctx.failures.append(f"{SOURCE}/calendar: unreadable ({exc}); the format may have changed")

    for dataset in LIVE:
        _check_and_fetch(ctx, dataset)

    for dataset in FROZEN:
        if ctx.archive.latest(SOURCE, dataset) is None:
            ctx.fetch_and_store(SOURCE, dataset, bulk_url(dataset), ext=".tsv.gz",
                                extra={"note": "frozen ECOICOP v1 dataset, copied once"})

    for name, url in METADATA.items():
        ctx.fetch_and_store(SOURCE, name, url, ext=".html", content_of=htmltext.visible_text)
    return dates


def _check_and_fetch(ctx: RunContext, dataset: str) -> None:
    if ctx.dry_run:
        ctx.planned.append(f"{SOURCE}/{dataset}: check {dataflow_url(dataset)}, download if updated")
        return
    tmp = ctx.archive.new_tmp()
    try:
        _, xml = ctx.http.get_bytes(dataflow_url(dataset), tmp)
    except FetchError as exc:
        ctx.archive.log_failure(SOURCE, dataset, dataflow_url(dataset), str(exc))
        ctx.failures.append(f"{SOURCE}/{dataset}: {exc}")
        return
    updated = last_update(xml)
    if updated is None:
        ctx.failures.append(f"{SOURCE}/{dataset}: no UPDATE_DATA in the dataflow; the format may have changed")
        return
    latest = ctx.archive.latest(SOURCE, dataset)
    if latest is not None and ctx.archive.manifest(latest).get("eurostat_updated") == updated:
        ctx.archive.log_unchanged_check(SOURCE, dataset, dataflow_url(dataset), f"last data update {updated}")
        return
    ctx.fetch_and_store(SOURCE, dataset, bulk_url(dataset), ext=".tsv.gz",
                        extra={"eurostat_updated": updated})
