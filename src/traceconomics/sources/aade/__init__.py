"""AADE, Greece's Independent Authority for Public Revenue: its yearly statistics on personal
income tax returns.

AADE publishes one workbook per tax year on its statistics page (`PAGE`). Each is archived once,
as served (a file's address carries its upload month, so a new year is a new link). The daily
job doesn't fetch them: AADE's CDN refuses requests from cloud servers (HTTP 403), and the
workbooks change once a year. They are downloaded by hand and added with
`traceconomics import --source aade`, which names the dataset with `dataset_for`, as a fetch would. The
consistency topic shows AADE's own totals, as published, next to other sources' answers to the
same question (household income; rent declared). AADE's terms allow reuse if the information is
reproduced accurately and AADE is cited, and forbid modifying it: so we never re-add its regions
or rescale its figures, we read its own all-regions total (see `parse`).
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urljoin

from traceconomics.backfill import slug

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
    """One archive dataset per workbook: `pit-<file name>`, e.g. pit-sd-fp-22f-3.

    Takes an address or a bare file name (a workbook downloaded by hand).
    """
    return "pit-" + slug(unquote(url.rsplit("/", 1)[-1]).rsplit(".", 1)[0])

