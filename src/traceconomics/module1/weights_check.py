"""The newest year's weights follow rule N: checked in every release build, from the outputs.

Module 1's default timing rule (rule N, `schedule.py`) decides which survey's spending pattern
each index year uses. Its unit tests check the rule; this check, a step of every release build,
checks that the outputs really used it for the year that changes: the newest. That year's weights
switch when a new year starts (January's release) and when a new survey year arrives, and no
published figure would show a wrong switch: ELSTAT's CPI check covers ELSTAT's basket, not ours.

Rule N for the newest year y, restated here rather than called, so a mistake in either fails:
- final, from survey y-1, when we hold it;
- otherwise a first estimate, from the newest survey we hold whose public file was out before
  1 January of y (dates in `data/hbs_puf_releases.toml`).
The weights must also reach the series' last year: a schedule that stops early leaves the newest
months without weights.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from traceconomics.module1.schedule import FINAL, FIRST, releases as puf_releases

# One series under rule N: its options apart from the timing rule.
SERIES = ("grouping", '"group"', "spending", "imputed_rent", "price_source", "tutoring")


def expected(year: int, held: set[int], releases: dict[int, dict]) -> tuple[int, str] | None:
    """(survey, status) rule N gives the index year `year`; None if no survey can be used."""
    if year - 1 in held:
        return year - 1, FINAL
    ready = [h for h in held if h in releases and releases[h]["available"] < date(year, 1, 1)]
    return (max(ready), FIRST) if ready else None


def held_surveys(con: duckdb.DuckDBPyConnection) -> set[int]:
    """The survey years whose weights the store holds."""
    rows = con.execute(
        "SELECT DISTINCT ref_period FROM observations WHERE dataset = 'oet-local:hbs_weights' ORDER BY 1"
    ).fetchall()
    return {int(r[0]) for r in rows}


def check(folder: Path, held: set[int], releases: dict[int, dict] | None = None) -> list[str]:
    """Problems with the newest year's weights in the module 1 outputs `folder` (gr/m1); none: ok."""
    releases = puf_releases() if releases is None else releases
    con = duckdb.connect()
    keys = ", ".join(SERIES)
    rows = con.execute(f"""
        SELECT DISTINCT {keys}, CAST(ref_period AS INTEGER), CAST(survey AS INTEGER), weights_status
        FROM '{(folder / "m1_weights_used.parquet").as_posix()}' WHERE weights_timing = 'N'
        ORDER BY ALL""").fetchall()
    newest: dict[tuple, tuple[int, int, str]] = {}
    for *series, year, survey, status in rows:
        if tuple(series) not in newest or year > newest[tuple(series)][0]:
            newest[tuple(series)] = (year, survey, status)
    last_index = {
        tuple(r[:-1]): r[-1]
        for r in con.execute(f"""
            SELECT {keys}, max(CAST(left(ref_period, 4) AS INTEGER))
            FROM '{(folder / "m1_index.parquet").as_posix()}' WHERE weights_timing = 'N'
            GROUP BY ALL ORDER BY ALL""").fetchall()
    }
    # One line per problem: the same group under other options (spending, rent, ...) reads the same.
    problems = set()
    for series, (year, survey, status) in newest.items():
        name = "/".join(series[:2])
        want = expected(year, held, releases)
        if want != (survey, status):
            problems.add(f"{year}: {name} uses survey {survey} ({status}), rule N gives {want or 'none'}")
        last = last_index.get(series)
        if last is not None and last != year:
            problems.add(f"{name}: weights end in {year}, its index in {last}")
    return sorted(problems)
