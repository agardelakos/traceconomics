"""The versioned mapping tables (package data), read with the standard library.

The price pipeline needs them too (to bring the 2009-2010 CPI tables into COICOP 2018), and it
must run without the optional microdata dependencies. How the tables are built is in
`traceconomics.local.mapping`.
"""

from __future__ import annotations

import csv
import io
from importlib import resources

from traceconomics.checks import require

V1_TO_2018 = "coicop_v1_2018.csv"
OLD_TO_V1 = "hbs_2008_2014_v1.csv"
FIELDS = ("from_code", "to_code", "share", "method", "note")


def read(name: str) -> list[dict]:
    """One table's rows, with `share` as a float. Every source code's shares must add up to 1."""
    text = resources.files("traceconomics.data").joinpath(name).read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    reader = csv.DictReader(io.StringIO(body))
    require(tuple(reader.fieldnames or ()) == FIELDS, f"{name}: columns {reader.fieldnames}")
    rows = [{**r, "share": float(r["share"])} for r in reader]
    sums: dict[str, float] = {}
    for r in rows:
        sums[r["from_code"]] = sums.get(r["from_code"], 0.0) + r["share"]
    bad = [code for code, s in sums.items() if abs(s - 1) >= 1e-9]
    require(not bad, f"{name}: shares that don't add up to 1 for {bad[:5]}")
    return rows
