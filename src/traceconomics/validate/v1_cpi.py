"""V1-CPI: rebuild the official Greek CPI from ELSTAT's table 07.

Each year's table 07 gives every item's monthly index and that year's
weights, plus the overall index. Linking each year at December with those
weights and chaining must give back the overall index.

That holds from 2014, the period checked strictly. Before that, the CPI was
not re-linked every December: the weights in the 2011, 2012 and 2013 tables
are identical, i.e. a fixed basket. Those years, in their re-issued form
(COICOP 2018, 2020=100), don't break down exactly into item indices times
weights by any linking rule we tried (errors up to about 1%), so they are
reported, not checked.
"""

from __future__ import annotations

import re
from pathlib import Path

from traceconomics.archive.store import Archive
from traceconomics.engine import chain
from traceconomics.sources.elstat.parse import TOTAL, Table07, parse
from traceconomics.validate.compare import Comparison, compare

ENGLISH_TABLE07 = re.compile(r"DKT87_TS_MM_01_(\d{4})_\d\d_\d{4}_07_F_EN\.xlsx?$")


def archived_files(archive: Archive) -> dict[int, Path]:
    """The newest archived English table 07 per year."""
    newest: dict[str, dict] = {}
    for rec in archive.index():
        if rec.get("status") == "stored" and rec.get("source") == "elstat" and rec.get("dataset", "").startswith("doc-"):
            newest[rec["dataset"]] = rec
    out: dict[int, tuple[str, Path]] = {}
    for rec in newest.values():
        m = ENGLISH_TABLE07.search(archive.manifest(rec).get("original_name", ""))
        if m:
            year = int(m.group(1))
            if year not in out or rec["retrieved_at"] > out[year][0]:
                out[year] = (rec["retrieved_at"], archive.root / rec["path"])
    return {y: p for y, (_, p) in sorted(out.items())}


def assemble(tables: list[Table07]):
    """(weights by year, item indices, official overall index, link-month disagreements).

    A December appears twice: as a month in its own year's file and as the
    link month of the next year's file (from 2014). Linking uses the next
    year's copy, as ELSTAT does; disagreements are counted for the report.
    """
    weights, prices, official = {}, {}, {}
    disagreements = 0
    for t in sorted(tables, key=lambda t: t.year):
        weights[t.year] = {c: w for c, w in t.weights.items() if c != TOTAL}
        link = f"{t.year - 1}-12"
        for code, series in t.indices.items():
            target = official if code == TOTAL else prices.setdefault(code, {})
            for period, v in series.items():
                if period == link and period in target and abs(target[period] - v) > 1e-9:
                    disagreements += 1
                target[period] = v
    return weights, prices, official, disagreements


CHECKED_FROM = 2014   # first year linked at December; see the module docstring


def _compare(name, weights, prices, official, first, last):
    result = chain(weights, prices, first_year=first, last_year=last,
                   base_value=official[f"{first - 1}-12"], periods=set(official))
    return compare(name, result, official)


def run(tables: list[Table07]) -> tuple[Comparison, Comparison | None, int]:
    """(the strict check from 2014, a report on earlier years if present, link-month disagreements)."""
    weights, prices, official, disagreements = assemble(tables)
    last = max(weights)
    first = max(CHECKED_FROM, min(weights) + 1)
    checked = _compare(f"CPI, finest detail, {first} on", weights, prices, official, first, last)
    earlier = None
    if min(weights) < CHECKED_FROM - 1:
        earlier = _compare(f"CPI, {min(weights) + 1}-{CHECKED_FROM - 1} (report only: fixed basket then)",
                           weights, prices, official, min(weights) + 1, CHECKED_FROM - 1)
    return checked, earlier, disagreements


def run_archive(archive: Archive) -> tuple[Comparison, Comparison | None, int, dict[int, Path]]:
    files = archived_files(archive)
    checked, earlier, disagreements = run([parse(p) for p in files.values()])
    return checked, earlier, disagreements, files
