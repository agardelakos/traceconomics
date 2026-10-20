"""Read Eurostat's bulk TSV files (one per dataset, all countries) into long form.

The format: the first column holds the series key, comma-separated, under a
header like `freq,unit,coicop18,geo\\TIME_PERIOD`; then one column per period.
A cell is a number, a number and flags (`105.23 d`), or `:` for no value,
possibly with flags (`: u`). Empty cells with flags are kept, without a value.

A file has tens of millions of cells, so the work is done in DuckDB SQL
rather than row by row in Python.

The output keeps each value exactly as published (`value_text`) next to the
number, and the flags as published. Two codes are translated on the way in:
countries to ISO 3166 (Greece is EL at Eurostat, GR here), and spending
categories without Eurostat's "CP" prefix, with all items as TOTAL.
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb

from traceconomics.catalog import DatasetSpec, geo
from traceconomics.checks import FormatError, examples, require

# Bump when parsing changes in a way that changes the output: the store then re-parses.
PARSER_VERSION = "1"

PERIOD = {"M": re.compile(r"^\d{4}-(0[1-9]|1[0-2])$"), "A": re.compile(r"^\d{4}$")}

# Eurostat observation flags: letters from its code list (b break, d definition
# differs, e estimated, f forecast, i see metadata, m missing, n not significant,
# p provisional, u low reliability) plus c (confidential), and "@C", which the
# ECOICOP v1 files use for confidential values.
FLAG = re.compile(r"^(@C|[bcdefimnpu]+)$")


@dataclass(frozen=True)
class Parsed:
    table: str            # DuckDB table holding the result
    rows: int             # observations, including flagged cells without a value
    values: int           # observations with a number
    periods: tuple[str, str]
    series: int


def header(path: Path) -> tuple[list[str], list[str]]:
    """(key dimensions, periods) from the first line of a bulk file."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        cols = f.readline().rstrip("\r\n").split("\t")
    require(len(cols) > 1 and "\\" in cols[0], f"{path.name}: not a Eurostat bulk TSV header: {cols[0][:80]!r}")
    dims_part, _, time_part = cols[0].partition("\\")
    require(time_part == "TIME_PERIOD", f"{path.name}: expected TIME_PERIOD after the key, got {time_part!r}")
    return dims_part.split(","), [c.strip() for c in cols[1:]]


def parse(con: duckdb.DuckDBPyConnection, path: Path, spec: DatasetSpec, table: str = "parsed") -> Parsed:
    """Parse one bulk file into `table` (replaced if it exists). Raises FormatError on any surprise."""
    dims, periods = header(path)
    require(tuple(dims) == spec.dimensions,
            f"{path.name}: key dimensions are {dims}, expected {list(spec.dimensions)} for {spec.id}")
    pattern = PERIOD[spec.freq]
    bad = [p for p in periods if not pattern.match(p)]
    require(not bad, f"{path.name}: unexpected period columns {examples(bad)}")

    first = f"{','.join(dims)}\\TIME_PERIOD"
    key_cols = [f"split_part(\"{first}\", ',', {i + 1}) AS {d}" for i, d in enumerate(dims)]
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _wide AS
        SELECT * FROM read_csv('{path.as_posix()}', delim='\t', header=true, all_varchar=true,
                               compression='gzip', quote='', escape='', auto_detect=false,
                               columns={_columns(first, periods)})
    """)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _cells AS
        WITH u AS (UNPIVOT _wide ON COLUMNS(* EXCLUDE ("{first}")) INTO NAME period VALUE raw)
        SELECT {', '.join(key_cols)}, trim(period) AS ref_period, trim(raw) AS raw
        FROM u WHERE trim(raw) <> ':'
    """)
    con.execute("DROP TABLE _wide")

    geo_sql = _geo_sql(spec.source)
    coicop_sql = _coicop_sql(spec.coicop) if spec.coicop else None
    select = []
    for d in dims:
        if d == "geo":
            select.append(f"{geo_sql} AS geo")
        elif d == spec.coicop:
            select.append(f"{coicop_sql} AS {d}")
        else:
            select.append(d)
    number = "CASE WHEN starts_with(raw, ':') THEN NULL ELSE split_part(raw, ' ', 1) END"
    rest = ("CASE WHEN starts_with(raw, ':') THEN substr(raw, 2) "
            "ELSE substr(raw, length(split_part(raw, ' ', 1)) + 1) END")
    con.execute(f"""
        CREATE OR REPLACE TABLE {table} AS
        SELECT {', '.join(select)}, ref_period,
               {number} AS value_text,
               TRY_CAST({number} AS DOUBLE) AS value,
               nullif(trim({rest}), '') AS flags
        FROM _cells
    """)
    con.execute("DROP TABLE _cells")

    _check(con, table, spec, path)
    rows, values, series = con.execute(
        f"SELECT count(*), count(value), count(DISTINCT ({', '.join(dims)})) FROM {table}").fetchone()
    require(rows > 0, f"{path.name}: no values at all")
    return Parsed(table=table, rows=rows, values=values, periods=(periods[0], periods[-1]), series=series)


def _columns(first: str, periods: list[str]) -> str:
    # Every column as text; the period headers keep the trailing space Eurostat writes, so
    # name them as read and trim later.
    names = [first] + periods
    return "{" + ", ".join(f"'{n}': 'VARCHAR'" for n in names) + "}"


def _geo_sql(source: str) -> str:
    rename = geo(source).rename
    if not rename:
        return "geo"
    cases = " ".join(f"WHEN '{a}' THEN '{b}'" for a, b in sorted(rename.items()))
    return f"CASE geo {cases} ELSE geo END"


def _coicop_sql(col: str) -> str:
    return (f"CASE WHEN {col} IN ('TOTAL', 'CP00') THEN 'TOTAL' "
            f"WHEN regexp_full_match({col}, 'CP[0-9]+') THEN substr({col}, 3) ELSE {col} END")


def _check(con: duckdb.DuckDBPyConnection, table: str, spec: DatasetSpec, path: Path) -> None:
    unparsed = con.execute(
        f"SELECT DISTINCT value_text FROM {table} WHERE value IS NULL AND value_text IS NOT NULL LIMIT 6"
    ).fetchall()
    require(not unparsed, f"{path.name}: values that aren't numbers: {examples(v for (v,) in unparsed)}")

    flags = [f for (f,) in con.execute(f"SELECT DISTINCT flags FROM {table} WHERE flags IS NOT NULL").fetchall()]
    bad = [f for f in flags if not FLAG.match(f)]
    require(not bad, f"{path.name}: unknown observation flags {examples(bad)}")

    empty = [d for d in spec.dimensions
             if con.execute(f"SELECT count(*) FROM {table} WHERE {d} = ''").fetchone()[0]]
    require(not empty, f"{path.name}: empty codes in {empty}")

    geos = [g for (g,) in con.execute(f"SELECT DISTINCT geo FROM {table}").fetchall()]
    unknown = [g for g in geos if not geo(spec.source).is_known(g)]
    require(not unknown, f"{path.name}: unknown country codes {examples(unknown)}")

    dup = con.execute(f"""
        SELECT {', '.join(spec.dimensions)}, ref_period FROM {table}
        GROUP BY ALL HAVING count(*) > 1 LIMIT 3""").fetchall()
    if dup:
        raise FormatError(f"{path.name}: the same series and period appear twice, e.g. {dup[0]}")
