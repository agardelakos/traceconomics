"""V1: rebuild a country's official all-items HICP from Eurostat's own sub-indices and item weights.

Eurostat publishes, per country, the index of every spending category
(`prc_hicp_minr`) and each category's weight in the basket (`prc_hicp_iw`,
per mille, already price-updated to December of the previous year). Linking
each year at December and chaining must give back the official all-items
index. The check runs at several depths: divisions, groups and classes from
1997, and the finest published detail (subclasses) from 2015, when their
weights start.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from traceconomics import catalog
from traceconomics.engine import chain
from traceconomics.engine.tree import at_level
from traceconomics.sources.eurostat import parse
from traceconomics.validate.compare import Comparison, compare

LEVELS = {"divisions": 2, "groups": 3, "classes": 4, "finest detail": None}
FIRST_YEAR = {"divisions": 1997, "groups": 1997, "classes": 1997, "finest detail": 2015}


def load(con: duckdb.DuckDBPyConnection, minr: Path, iw: Path, geo: str):
    """(weights by year, item indices, official index, official annual rates) for one country."""
    parse.parse(con, minr, catalog.dataset("eurostat:prc_hicp_minr"), table="minr")
    parse.parse(con, iw, catalog.dataset("eurostat:prc_hicp_iw"), table="iw")
    prices: dict[str, dict[str, float]] = {}
    for code, period, value in con.execute(
            "SELECT coicop18, ref_period, value FROM minr WHERE geo = ? AND unit = 'I25' AND value IS NOT NULL",
            [geo]).fetchall():
        prices.setdefault(code, {})[period] = value
    rates = {p: v for p, v in con.execute(
        "SELECT ref_period, value FROM minr WHERE geo = ? AND unit = 'RCH_A' AND coicop18 = 'TOTAL' "
        "AND value IS NOT NULL", [geo]).fetchall()}
    weights: dict[int, dict[str, float]] = {}
    for code, year, value in con.execute(
            "SELECT coicop18, ref_period, value FROM iw WHERE geo = ? AND value IS NOT NULL", [geo]).fetchall():
        weights.setdefault(int(year), {})[code] = value
    return weights, prices, prices.get("TOTAL", {}), rates


def run(weights, prices, official, rates, last_year: int) -> list[Comparison]:
    out = []
    for name, digits in LEVELS.items():
        first = FIRST_YEAR[name]
        w = {y: (at_level(ws, digits) if digits else ws) for y, ws in weights.items()}
        base = official.get(f"{first - 1}-12")
        if base is None:
            continue
        result = chain(w, prices, first_year=first, last_year=last_year, base_value=base, periods=set(official))
        out.append(compare(name, result, official, rates))
    return out
