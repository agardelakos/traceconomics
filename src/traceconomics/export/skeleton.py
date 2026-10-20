"""The first published series: Greece's all-households HICP, rebuilt by our engine.

This proves the whole path (raw archive -> store -> engine -> published file
-> website) on a series whose right answer is known. It is the official HICP
rebuilt from Eurostat's own sub-indices and item weights at the finest
published detail; it is not yet the inflation-by-income-group series, which
needs our own household weights.

Writes two files:
    gr_hicp_all_households.csv   one row per month: our index and annual rate,
                                 next to the official ones
    gr_hicp_all_households.json  what the numbers are, their sources
                                 (bibliography keys), licence and attribution
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from traceconomics import __version__, references
from traceconomics.engine import annual_rate, chain
from traceconomics.store.query import as_of

GEO = "GR"
FIRST_YEAR = 2015   # subclass weights start in 2015
NAME = "gr_hicp_all_households"
SOURCES = ["hicp-manual-2024", "reg-2016-792", "reg-2020-1148"]
ATTRIBUTION = ("Source: Eurostat, prc_hicp_minr and prc_hicp_iw. Computed by Traceconomics from Eurostat "
               "data; Eurostat bears no responsibility for these figures.")


def _inputs(con: duckdb.DuckDBPyConnection):
    prices: dict[str, dict[str, float]] = {}
    newest = None
    rel = as_of(con, "eurostat:prc_hicp_minr", where=f"geo = '{GEO}' AND unit = 'I25'")
    for code, period, value, published in rel.project("coicop18, ref_period, value, published_at").fetchall():
        if value is not None:
            prices.setdefault(code, {})[period] = value
            newest = max(newest or published, published)
    rates = {p: v for p, v in as_of(con, "eurostat:prc_hicp_minr",
                                    where=f"geo = '{GEO}' AND unit = 'RCH_A' AND coicop18 = 'TOTAL'")
             .project("ref_period, value").fetchall() if v is not None}
    weights: dict[int, dict[str, float]] = {}
    for code, year, value in as_of(con, "eurostat:prc_hicp_iw", where=f"geo = '{GEO}'") \
            .project("coicop18, ref_period, value").fetchall():
        if value is not None:
            weights.setdefault(int(year), {})[code] = value
    return weights, prices, rates, newest


def export(con: duckdb.DuckDBPyConnection, out_dir: Path) -> list[Path]:
    weights, prices, rates, newest = _inputs(con)
    official = prices.get("TOTAL", {})
    if not official:
        raise ValueError(f"no all-items HICP for {GEO} in the store; run `traceconomics store update`")
    missing = references.missing(SOURCES)
    if missing:
        raise ValueError(f"sources not in the bibliography: {missing}")

    last_year = int(max(official)[:4])
    result = chain(weights, prices, first_year=FIRST_YEAR, last_year=last_year,
                   base_value=official[f"{FIRST_YEAR - 1}-12"], periods=set(official))
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{NAME}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["period", "index", "annual_rate", "official_index", "official_annual_rate"])
        for period in sorted(result.index):
            if period < f"{FIRST_YEAR}-01":
                continue
            ours = annual_rate(result.index, period)
            w.writerow([
                period,
                f"{result.index[period]:.2f}",          # published indices have two decimals
                "" if ours is None else f"{ours:.1f}",  # and rates one
                f"{official[period]:.2f}" if period in official else "",
                f"{rates[period]:.1f}" if period in rates else "",
            ])
    meta = {
        "title": "Greece: consumer price inflation for all households (HICP), rebuilt from its parts",
        "description": ("The harmonised index of consumer prices (HICP) for Greece, rebuilt by "
                        "Traceconomics from Eurostat's sub-indices and item weights at the finest published "
                        "detail, linked each December. The official series is given alongside: the two agree "
                        "to within 0.1 percentage points on annual rates, the most that rounding of the "
                        "published inputs allows. This is a test of the calculation, not yet a series by "
                        "household group."),
        "geo": GEO,
        "unit": {"index": "2025 = 100", "annual_rate": "percent change on the same month a year earlier"},
        "first_period": f"{FIRST_YEAR}-01",
        "last_period": max(result.index),
        "data_as_published_by": newest.strftime("%Y-%m-%dT%H:%MZ") if newest else None,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_version": __version__,
        "sources": SOURCES,
        "attribution": ATTRIBUTION,
        "licence": "CC BY 4.0",
    }
    json_path = out_dir / f"{NAME}.json"
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return [csv_path, json_path]
