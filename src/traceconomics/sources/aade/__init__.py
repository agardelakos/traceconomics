"""AADE, Greece's Independent Authority for Public Revenue: its yearly statistics on personal
income tax returns.

AADE publishes one workbook per tax year on its statistics page. Each is archived once, as
served (a file's address carries its upload month, so a new year is a new link). The
consistency topic shows AADE's own totals, as published, next to other sources' answers to the
same question (household income; rent declared). AADE's terms allow reuse if the information is
reproduced accurately and AADE is cited, and forbid modifying it: so we never re-add its regions
or rescale its figures, we read its own all-regions total (see `parse`).
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urljoin

from traceconomics import htmltext
from traceconomics.backfill import slug
from traceconomics.sources.base import RunContext

SOURCE = "aade"
PAGE = "https://www.aade.gr/en/perfomance-reports-accountability/statistics/annual-statistical-reports-natural-persons"
LINK = re.compile(r'href="(/sites/default/files/[^"]+\.xlsx)"')


def workbook_links(page_html: str) -> list[str]:
    """Every yearly workbook linked from the statistics page, as absolute addresses, in page order."""
    seen, out = set(), []
    for href in LINK.findall(page_html):
        url = urljoin(PAGE, href)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def dataset_for(url: str) -> str:
    """One archive dataset per workbook: `pit-<file name>`, e.g. pit-sd-fp-22f-3."""
    return "pit-" + slug(unquote(url.rsplit("/", 1)[1]).rsplit(".", 1)[0])


def run(ctx: RunContext) -> None:
    """The page on every run (one request); each workbook only the first time it is linked."""
    _, data = ctx.fetch_and_store(SOURCE, "page-annual-reports", PAGE, ext=".html", content_of=htmltext.visible_text)
    if data is None:
        return
    for url in workbook_links(data.decode("utf-8", "replace")):
        dataset = dataset_for(url)
        if ctx.archive.latest(SOURCE, dataset) is None:
            ctx.fetch_and_store(SOURCE, dataset, url, ext=".xlsx",
                                extra={"original_name": unquote(url.rsplit("/", 1)[1])})
