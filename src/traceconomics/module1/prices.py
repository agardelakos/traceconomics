"""CPI prices from the store, one block per year, and the price ratios built from them.

ELSTAT publishes the CPI's item indices in one file a year (table 07). The file for year y holds
the twelve months of y and, from 2014, December of y-1, the month each year is linked to. The
same December can therefore appear twice (in its own year's file and as the next year's link
month), and the two copies needn't agree to the last digit. So each year keeps its own block:
the months of y from the file for y, and its December y-1 from the same file, or, for files
without that column (2010-2013), from the previous year's file.

Ratios over several years (price-updating an older survey) are chained through each year's own
block, never taken between two blocks' levels.
"""

from __future__ import annotations

import duckdb

from traceconomics.checks import require
from traceconomics.engine.chain import Prices, link_month, months
from traceconomics.engine.tree import ancestors

DATASET = "elstat:cpi07"


def cpi_blocks(con: duckdb.DuckDBPyConnection, when=None) -> dict[int, Prices]:
    """{year: {code: {"YYYY-MM": index}}}: each year's months plus its link month, as known at `when`."""
    cond = "dataset = $d AND unit = 'I20' AND freq = 'M'"
    params = {"d": DATASET}
    if when is not None:
        cond += " AND published_at <= $when"
        params["when"] = when
    rows = con.execute(f"""
        SELECT archive_dataset, coicop18, ref_period, value FROM observations WHERE {cond}
        QUALIFY row_number() OVER (PARTITION BY archive_dataset, key, ref_period
                                   ORDER BY published_at DESC, retrieved_at DESC) = 1
            AND status <> 'withdrawn'
        ORDER BY archive_dataset, coicop18, ref_period    -- fixed order: see load_baskets
    """, params).fetchall()
    by_file: dict[str, Prices] = {}
    for archive_dataset, code, period, value in rows:
        if value is not None:
            by_file.setdefault(archive_dataset, {}).setdefault(code, {})[period] = value
    files: dict[int, str] = {}
    for name, prices in by_file.items():
        year = max(int(p[:4]) for series in prices.values() for p in series)
        require(year not in files, f"two table 07 files for {year}: {files.get(year)} and {name}")
        files[year] = name
    blocks: dict[int, Prices] = {}
    for year in sorted(files):
        own = by_file[files[year]]
        wanted = set(months(year)) | {link_month(year)}
        block = {c: {p: v for p, v in s.items() if p in wanted} for c, s in own.items()}
        previous = by_file.get(files.get(year - 1, ""), {})
        for code, series in block.items():
            dec = link_month(year)
            if dec not in series and dec in previous.get(code, {}):
                series[dec] = previous[code][dec]
        blocks[year] = block
    return blocks


def _first_with(block: Prices, code: str, periods) -> str | None:
    """The code, or its nearest ancestor, with an index for every one of `periods` in this block."""
    for c in [code, *ancestors(code)]:
        series = block.get(c, {})
        if all(series.get(p) for p in periods):
            return c
    return None


def year_ratio(blocks: dict[int, Prices], code: str, year: int) -> tuple[float, str] | None:
    """December of `year` over December of year-1, within year's block."""
    block = blocks.get(year, {})
    dec, prev = f"{year}-12", link_month(year)
    used = _first_with(block, code, [dec, prev])
    return None if used is None else (block[used][dec] / block[used][prev], used)


def update_factor(blocks: dict[int, Prices], code: str, survey: int, year: int) -> tuple[float, list[str]] | None:
    """P(December of year-1) / P(average of the survey year), chained through each year's block,
    for the code or its nearest ancestor with the data; None if no level has them.

    Within the survey year: December over the year's average. Then, for every later year up to
    year-1, that year's December over the one before it."""
    block = blocks.get(survey, {})
    ms = months(survey)
    used = _first_with(block, code, ms)
    if used is None:
        return None
    series = block[used]
    factor = series[f"{survey}-12"] / (sum(series[m] for m in ms) / 12)
    path = [used]
    for k in range(survey + 1, year):
        r = year_ratio(blocks, code, k)
        if r is None:
            return None
        factor *= r[0]
        path.append(r[1])
    return factor, path


HICP_DATASET = "eurostat:prc_hicp_minr"


def hicp_blocks(con: duckdb.DuckDBPyConnection, when=None, geo: str = "GR") -> dict[int, Prices]:
    """{year: {code: {"YYYY-MM": index}}} from Eurostat's HICP item indices (2025=100), as known
    at `when`. Eurostat publishes each item as one continuous chain-linked series, so a year's
    block is simply its twelve months and the December before, cut from that series; unlike the
    CPI there is no second copy of a December to choose between."""
    cond = "dataset = $d AND geo = $geo AND unit = 'I25' AND freq = 'M'"
    params = {"d": HICP_DATASET, "geo": geo}
    if when is not None:
        cond += " AND published_at <= $when"
        params["when"] = when
    rows = con.execute(f"""
        SELECT coicop18, ref_period, value FROM observations WHERE {cond}
        QUALIFY row_number() OVER (PARTITION BY key, ref_period ORDER BY published_at DESC, retrieved_at DESC) = 1
            AND status <> 'withdrawn'
        ORDER BY coicop18, ref_period                     -- fixed order: see load_baskets
    """, params).fetchall()
    series: Prices = {}
    for code, period, value in rows:
        if value is not None and code[:1].isdigit():
            series.setdefault(code, {})[period] = value
    years = sorted({int(p[:4]) for s in series.values() for p in s})
    blocks: dict[int, Prices] = {}
    for year in years:
        # The months the year has so far (all twelve, except in the current year).
        have = [m for m in months(year) if any(m in s for s in series.values())]
        wanted = [link_month(year), *have]
        # An item belongs to the year only if it has the link month and every month so far:
        # a series that stops (education not by level ends in 2014-12) or starts in December
        # (games of chance, 2025-12) must not seem to price the year from one month.
        blocks[year] = {c: {p: s[p] for p in wanted} for c, s in series.items()
                        if all(p in s for p in wanted)}
    return blocks
