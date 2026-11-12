"""Eurostat datasets, all countries: the HICP, the EU-SILC income limits (`ilc_di01`), and the
tables the consistency topic lines up against each other ("same question, different sources").

Each live dataset is downloaded in full (one compressed TSV file) only when
Eurostat's "last data update" time has changed since our last copy. Eurostat
keeps flash and first-final values itself (prc_hicp_fpd), so our copies mainly
add later revisions. The ECOICOP v1 datasets are frozen since 2025-12 and are
copied once, in case they are removed. `ilc_di01` (income by fifths and tenths, in euros and in
purchasing power standards) is checked like the HICP, on every run the job makes (a due day, or
one forced by hand): the check is one small request, and the file changes a few times a year.

The consistency topic's tables are checked the same way: household consumption by purpose
(`nama_10_co3_p3`: rent paid, CP041) and household income (`nasa_10_nf_tr`, B6G) from the
national accounts; tenure (`ilc_lvho02`) and mean income (`ilc_di03`) from EU-SILC; unemployment
from the labour force survey (`une_rt_m`, `une_rt_a`). The censuses' household tables by tenure
(2011, 2021) never change and are copied once.
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

LIVE = (
    "prc_hicp_minr",
    "prc_hicp_iw",
    "prc_hicp_fpd",
    "ilc_di01",
    "nama_10_co3_p3",
    "nasa_10_nf_tr",
    "ilc_lvho02",
    "ilc_di03",
    "une_rt_m",
    "une_rt_a",
)
FROZEN = ("prc_hicp_midx", "prc_hicp_inw", "prc_hicp_fp", "cens_11htts_r2", "cens_21hhct_r3")
METADATA = {"esms-prc_hicp": "https://ec.europa.eu/eurostat/cache/metadata/en/prc_hicp_esms.htm"}

CALENDAR_URL = (
    "https://ec.europa.eu/eurostat/o/calendars/eventsJson?theme=0&category=0&keywords="
    "&isEuroindicator=true&authorInclude=&authorExclude=&start={start}&end={end}"
)

UPDATE_DATA = re.compile(
    r"<c:AnnotationTitle>([^<]+)</c:AnnotationTitle>\s*<c:AnnotationType>UPDATE_DATA</c:AnnotationType>"
)


def bulk_url(dataset: str, api: str = API) -> str:
    return f"{api}/sdmx/2.1/data/{dataset.upper()}/?format=TSV&compressed=true"


def dataflow_url(dataset: str, api: str = API, agency: str = "ESTAT") -> str:
    return f"{api}/sdmx/2.1/dataflow/{agency}/{dataset.upper()}/latest"


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
    _, data = ctx.fetch_and_store(SOURCE, "calendar", calendar_url(ctx.today), ext=".json", content_of=calendar_content)
    if data:
        try:
            dates = release_dates(data)
        except (ValueError, KeyError) as exc:
            ctx.failures.append(f"{SOURCE}/calendar: unreadable ({exc}); the format may have changed")

    for dataset in LIVE:
        check_and_fetch(ctx, dataset)

    for dataset in FROZEN:
        if ctx.archive.latest(SOURCE, dataset) is None:
            note = (
                "a census table, fixed, copied once"
                if dataset.startswith("cens_")
                else "frozen ECOICOP v1 dataset, copied once"
            )
            ctx.fetch_and_store(SOURCE, dataset, bulk_url(dataset), ext=".tsv.gz", extra={"note": note})

    for name, url in METADATA.items():
        ctx.fetch_and_store(SOURCE, name, url, ext=".html", content_of=htmltext.visible_text)
    return dates


def check_and_fetch(
    ctx: RunContext, dataset: str, *, source: str = SOURCE, api: str = API, agency: str = "ESTAT"
) -> None:
    """Download `dataset` in full only if its "last data update" changed since our copy. The
    European Commission's other statistics sites (`ec_empl`) serve the same API, hence the
    parameters."""
    flow = dataflow_url(dataset, api, agency)
    if ctx.dry_run:
        ctx.planned.append(f"{source}/{dataset}: check {flow}, download if updated")
        return
    tmp = ctx.archive.new_tmp()
    try:
        _, xml = ctx.http.get_bytes(flow, tmp)
    except FetchError as exc:
        ctx.archive.log_failure(source, dataset, flow, str(exc))
        ctx.failures.append(f"{source}/{dataset}: {exc}")
        return
    updated = last_update(xml)
    if updated is None:
        ctx.failures.append(f"{source}/{dataset}: no UPDATE_DATA in the dataflow; the format may have changed")
        return
    latest = ctx.archive.latest(source, dataset)
    if latest is not None and ctx.archive.manifest(latest).get("eurostat_updated") == updated:
        ctx.archive.log_unchanged_check(source, dataset, flow, f"last data update {updated}")
        return
    ctx.fetch_and_store(source, dataset, bulk_url(dataset, api), ext=".tsv.gz", extra={"eurostat_updated": updated})
