"""V2: rebuild ELSTAT's published household spending from the survey microdata.

Table 1.03 gives the average monthly purchases of all households, by item.
The same figure from the microdata is the weighted mean of each household's
annual purchases, divided by 12. If our reading of the microdata and their
weights is right, the two agree to the cent.

They can't agree on items the public use file leaves out or cuts (tolls,
life insurance, "various services" and a few more), nor on
the totals that contain them. Those are listed, with the evidence, in
`data/hbs_puf_missing_items.toml`; a difference anywhere else is a failure.

The table also splits households into bands, and in some years the bands can
be rebuilt exactly from the microdata (`BANDED`). There each band is compared
the same way: that checks sums over a group of households, which is what the
spending shares are made of, and not just over all of them.

Where ELSTAT publishes coefficients of variation for mean purchases per division
(`data/hbs_published_cvs.toml`), the bootstrap that gives our shares their standard
errors is run on the same statistic and must give the same values (`cv_check`).
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import numpy as np
import pandas as pd

from traceconomics.archive.store import Archive
from traceconomics.checks import require
from traceconomics.local import bootstrap, puf
from traceconomics.local.groups import household_size
from traceconomics.local.shares import leaves
from traceconomics.local.puf import Survey
from traceconomics.sources.elstat import hbs_tables
from traceconomics.sources.elstat.hbs_tables import ALL, Table103

TOLERANCE = 0.015      # euros a month: the published figures are rounded to the cent
# Years whose PUF weights differ from the published tables: compared and
# reported, but not held to the cent.
REPORT_ONLY = (2014, 2015, 2018)
TABLE_103 = re.compile(r"SFA05_TB_AN_00_(\d{4})_103_F_EN\.xlsx?$")
MAX_DIGITS = 5         # the microdata and the table share codes up to 5 digits
# Years whose bands the microdata rebuild exactly (every band's household count, then its
# spending to the cent): by monthly money income (HH095 / 12, rounded to the euro), or, in 2013,
# by household size. In the other years no income column, nor any sum of the income columns,
# reproduces the band counts (checked 2026-10-19), so ELSTAT banded them on an income the
# public file doesn't carry; there only all households are compared.
BANDED = {2010: "income", 2011: "income", 2012: "income", 2013: "size"}
BAND_NUMBER = re.compile(r"\d+")


@dataclass
class V2Result:
    year: int
    households_puf: float
    households_published: float
    compared: int = 0
    matched: int = 0
    excused: list[tuple[str, str, float, float | None]] = field(default_factory=list)
    mismatches: list[tuple[str, str, float, float | None]] = field(default_factory=list)  # code, label, published, ours
    group: str = ALL
    uncovered: float | None = None     # all households only, see `uncovered`

    @property
    def same_households(self) -> bool:
        return abs(self.households_puf - self.households_published) < 1.5   # 2020 differs by rounding

    @property
    def passed(self) -> bool:
        return self.same_households and not self.mismatches


@dataclass
class CVResult:
    year: int
    design: str
    rows: list[tuple[str, float, float]]      # code, published CV %, ours
    tolerance: dict[str, float]

    @property
    def passed(self) -> bool:
        return all(abs(ours - pub) <= self.tolerance[code] for code, pub, ours in self.rows)


def published_cvs() -> dict[int, dict]:
    data = tomllib.loads(resources.files("traceconomics.data").joinpath("hbs_published_cvs.toml").read_text(encoding="utf-8"))
    return {int(y): e for y, e in data.items()}


def cv_check(survey: Survey, published: dict[str, float], replicates: int = bootstrap.REPLICATES) -> CVResult:
    """Our bootstrap CV (%) of mean purchases per division against ELSTAT's.

    Allowed difference: the published rounding (0.05) plus three Monte Carlo standard errors of a
    CV estimated from B replicates, CV / sqrt(2 (B - 1)) (normal approximation)."""
    d = bootstrap.design(survey)
    require(d.status != "unavailable", f"{survey.year}: {d.note}")
    rng = np.random.default_rng([bootstrap.SEED, survey.year])
    rw = survey.households.weight.to_numpy(float)[:, None] * bootstrap.replicate_factors(d, replicates, rng)
    w = survey.households.weight.to_numpy(float)
    divisions = [c for c in survey.purchases if len(c) == 2 and c != "00"]
    rows, tolerance = [], {}
    for code, pub in sorted(published.items()):
        x = (survey.purchases[divisions].sum(axis=1) if code == "00" else survey.purchases[code]).to_numpy(float)
        mean = (x * w).sum() / w.sum()
        means = (x[:, None] * rw).sum(axis=0) / rw.sum(axis=0)
        rows.append((code, pub, round(float(means.std(ddof=1) / mean * 100), 2)))
        tolerance[code] = 0.05 + 3 * pub / np.sqrt(2 * (replicates - 1))
    return CVResult(survey.year, d.status, rows, tolerance)


def missing_items() -> dict[str, list[str]]:
    """{code: [years]} of items the PUF lacks or cuts, from the package data file."""
    data = tomllib.loads(resources.files("traceconomics.data").joinpath("hbs_puf_missing_items.toml").read_text(encoding="utf-8"))
    return {code: e["years"] for code, e in data.get("items", {}).items()}


def uncovered(survey: Survey, table: Table103, missing: dict[str, list] | None = None) -> tuple[float, dict[str, float]]:
    """The share of all households' purchases that the PUF lacks, and the euros a month per item.

    Per listed item: the published figure minus the PUF's (all of it where the PUF has no
    column), over published total purchases. The shares drop these items and rescale the rest,
    so this is the part of spending they don't describe. It can't be split by our groups: the
    PUF has no trace of who bought what it leaves out.
    """
    missing = missing_items() if missing is None else missing
    w = survey.households.weight
    gaps = {}
    for code, years in missing.items():
        if survey.year not in years:
            continue
        published = table.purchases.get(code, {}).get(ALL)
        require(published is not None, f"{survey.year}: listed missing item {code} isn't in table 1.03")
        ours = float((survey.purchases[code] * w).sum() / w.sum() / 12) if code in survey.purchases else 0.0
        gaps[code] = published - ours
    return sum(gaps.values()) / table.purchases["00"][ALL], gaps


def _excused(code: str, year: int, missing: dict[str, list]) -> bool:
    """A listed missing item, or a total that contains one (its parent, grandparent, ... or 00)."""
    for item, years in missing.items():
        if year in years and (item == code or item.startswith(code) or code == "00"):
            return True
    return False


def bands(survey: Survey, table: Table103, by: str) -> pd.Series:
    """Each household's band in the table (aligned with survey.households), from the band labels:
    "up 750", "751-1100", ..., "3501 and over" (euros a month), or "1 member", ..., "6 members and over"."""
    labels = table.groups[1:]
    numbers = [[int(n) for n in BAND_NUMBER.findall(b)] for b in labels]
    if by == "income":
        require(len(numbers[0]) == 1 and all(len(n) == 2 for n in numbers[1:-1]) and len(numbers[-1]) == 1,
                f"{survey.year}: unexpected income bands {labels}")
        edges = [n[-1] for n in numbers[:-1]]          # each band's top, which it includes
        value = (survey.households.money_income / 12).round().to_numpy()
        index = np.searchsorted(edges, value, side="left")
    elif by == "size":
        require([n for n in numbers] == [[k] for k in range(1, len(labels) + 1)],
                f"{survey.year}: unexpected size bands {labels}")
        size = household_size(survey).reindex(survey.households.hh)["size"].to_numpy()
        require(not np.isnan(size).any(), f"{survey.year}: households without person records can't be banded by size")
        index = np.minimum(size.astype(int), len(labels)) - 1
    else:
        raise ValueError(by)
    return pd.Series(np.array(labels, dtype=object)[index])


def compare(survey: Survey, table: Table103, missing: dict[str, list] | None = None,
            group: str = ALL, members: pd.Series | None = None) -> V2Result:
    """Compare one column of the table: all households, or one band given its member households."""
    missing = missing_items() if missing is None else missing
    keep = np.ones(len(survey.households), bool) if members is None else members.to_numpy(bool)
    w = survey.households.weight[keep]
    bought = survey.purchases[keep]
    total_w = w.sum()
    r = V2Result(year=survey.year, households_puf=float(total_w), households_published=table.households[group],
                 group=group)
    for code, by_group in sorted(table.purchases.items()):
        if len(code) > MAX_DIGITS:
            continue
        published = by_group.get(group)
        if published is None:
            continue
        if code == "00":
            # The sum of the finest codes, which is what the shares are built from. (Files up to
            # 2014 carry their own total, HE00, and every file its division totals; neither is
            # always that sum.)
            finest = leaves(bought.columns)
            ours = float(sum((bought[c] * w).sum() for c in finest) / total_w / 12)
        elif code in bought:
            ours = float((bought[code] * w).sum() / total_w / 12)
        else:
            ours = None
        r.compared += 1
        row = (code, table.labels.get(code, ""), published, None if ours is None else round(ours, 4))
        if ours is not None and abs(ours - published) <= TOLERANCE:
            r.matched += 1
        elif _excused(code, survey.year, missing):
            r.excused.append(row)
        else:
            r.mismatches.append(row)
    return r


def archived_tables(archive: Archive) -> dict[int, Path]:
    """The newest archived English table 1.03 per survey year."""
    found: dict[int, tuple[str, Path]] = {}
    for source, dataset in archive.datasets():
        if source != "elstat" or not dataset.startswith("doc-"):
            continue
        rec = archive.latest(source, dataset)
        m = TABLE_103.search(archive.manifest(rec).get("original_name") or "")
        if m and (int(m.group(1)) not in found or rec["retrieved_at"] > found[int(m.group(1))][0]):
            found[int(m.group(1))] = (rec["retrieved_at"], archive.root / rec["path"])
    return {y: p for y, (_, p) in sorted(found.items())}


def run(archive: Archive, years: list[int]) -> list[V2Result]:
    """All households for every year, then each band for the years in BANDED."""
    tables = archived_tables(archive)
    missing = missing_items()
    out = []
    for year in years:
        if year not in tables:
            raise FileNotFoundError(f"no archived table 1.03 for {year}")
        survey, table = puf.read(archive, year), hbs_tables.parse(tables[year], year)
        result = compare(survey, table, missing)
        result.uncovered = uncovered(survey, table, missing)[0]
        out.append(result)
        if year in BANDED:
            band = bands(survey, table, BANDED[year])
            for label in table.groups[1:]:
                out.append(compare(survey, table, missing, group=label, members=band == label))
    return out
