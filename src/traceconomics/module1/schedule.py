"""Which survey's spending pattern each index year uses: the weights-timing rule.

Rule N (the default): the weights for year y are, finally, those of survey y-1, the pattern the
law asks weights to represent (Reg. 2020/1148, Art. 3(1)(b): "representative of year t-1").
That survey's microdata come out about 16 months into year y, so until then year y uses a
first estimate: the newest survey whose microdata were available when the year began. When
survey y-1 arrives, year y is revised once, to the final weights.

For years computed after the fact, the final weights apply directly whenever survey y-1 exists.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from importlib import resources

FIRST, FINAL = "first", "final"


@dataclass(frozen=True)
class Entry:
    year: int            # the index year
    survey: int          # the survey whose shares are used
    status: str          # FIRST or FINAL
    valid_from: str      # first month the weights apply to
    basis: str           # why this survey, in words

    @property
    def price_update_from(self) -> int:
        """Shares are moved from the survey year's average prices to December of y-1."""
        return self.survey


def releases() -> dict[int, dict]:
    """{survey year: {"available": date, "basis": ..., "note": ...}} from the package data file."""
    data = tomllib.loads(resources.files("traceconomics.data").joinpath("hbs_puf_releases.toml").read_text(encoding="utf-8"))
    return {int(y): {**e, "available": date.fromisoformat(e["available"])} for y, e in data.items()}


def rule_n(years, surveys: set[int], release_dates: dict[int, dict] | None = None) -> list[Entry]:
    """The weights schedule for `years`, given the surveys we hold.

    Final where survey y-1 is held. Otherwise the first estimate: the newest held survey known to
    be available on 1 January of year y (from `release_dates`); a survey with no known date can't
    be a first estimate, and a year with no candidate is left out (and so is any later year,
    since a chain can't skip a year).
    """
    release_dates = releases() if release_dates is None else release_dates
    out = []
    for y in years:
        if y - 1 in surveys:
            out.append(Entry(y, y - 1, FINAL, f"{y}-01", f"survey {y - 1} (the year before)"))
            continue
        start = date(y, 1, 1)
        ready = [h for h in surveys if h in release_dates and release_dates[h]["available"] < start]
        if not ready:
            break
        h = max(ready)
        r = release_dates[h]
        out.append(Entry(y, h, FIRST, f"{y}-01",
                         f"survey {h}, the newest available on {start} ({r['basis']} {r['available']})"))
    return out


def elstat_rule(years, surveys: set[int], release_dates=None) -> list[Entry]:
    """ELSTAT's own rule for the CPI, for comparison only: survey y-2, price-updated to December
    y-1 (CPI quality report 2026; ELSTAT SIMS). Ends at the first year without its survey."""
    out = []
    for y in years:
        if y - 2 not in surveys:
            break
        out.append(Entry(y, y - 2, FINAL, f"{y}-01", f"survey {y - 2} (ELSTAT's rule, two years before)"))
    return out


def rule_f(years, surveys: set[int], release_dates=None, lag: int = 3) -> list[Entry]:
    """Rule F: weights fixed when the year begins and never revised.

    For years before our own archive existed, the microdata release dates can't be used: the
    public files for 2008-2017 were first issued in late 2018 or after (their files' own dates),
    so there was no "newest file in January" for most of the past. The rule is therefore stated
    as a fixed lag: survey y-3, the lag between a survey and the January after its microdata
    appear today. Starts at the first year whose survey is held; a year without its survey
    ends the schedule, since a chain can't skip a year."""
    out = []
    started = False
    for y in years:
        if y - lag not in surveys:
            if started:
                break
            continue
        started = True
        out.append(Entry(y, y - lag, FINAL, f"{y}-01", f"survey {y - lag} ({lag} years before; never revised)"))
    return out


def rule_u(years, surveys: set[int], release_dates=None) -> list[Entry]:
    """Rule U: the same year's survey, as in studies made after the fact (KEPE). Not a
    Laspeyres-type index (its weights aren't from a period before the prices); no
    price-updating is needed. Ends at the first year whose survey isn't held."""
    out = []
    for y in years:
        if y not in surveys:
            break
        out.append(Entry(y, y, FINAL, f"{y}-01", f"survey {y} (the same year)"))
    return out


RULES = {"N": rule_n, "F": rule_f, "U": rule_u}
