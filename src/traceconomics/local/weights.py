"""The whole run for one survey year: archived microdata -> weights table -> archive (source `oet-local`).

Per year, two CSV files, each opened by `#` lines with their provenance:

- `hbs-weights-gr-YYYY`: one row per spending concept, grouping, group, imputed-rent option and
  COICOP 2018 code:
  the share of the group's spending, its standard error, how many sampled households reported
  spending on it, and the publication tier;
- `hbs-groups-gr-YYYY`: one row per grouping and group: sample size, weighted households and
  people, and the year's facts (the part of purchases the microdata leave out, the
  standard-error design).

Only aggregates are written, and the files are meant to be published, so a count under 20 is
written as "<20" (as Eurostat does), never as a number. Cells under 20 keep their share: it is
used for computation, priced at the parent level.

The files hold no run date, so rerunning with the same inputs and code gives the same bytes and
the archive keeps a single copy.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from importlib import resources

import numpy as np
import pandas as pd

from traceconomics import __version__
from traceconomics.archive.store import Archive
from traceconomics.local import bootstrap, mapping, puf, v2
from traceconomics.local.groups import assign
from traceconomics.local.shares import PUBLISHED, SPENDING, memberships, shares
from traceconomics.sources.elstat import hbs_tables

SOURCE = "oet-local"
GEO = "GR"
WEIGHTS = "hbs-weights-gr-{year}"
GROUPS = "hbs-groups-gr-{year}"
IMPUTED_RENT = {1: "excluded", 2: "included"}
HH_WEIGHTING = "plutocratic"        # each household counts in proportion to what it spends
TUTORING = "priced"                 # tutoring stays in the basket (the "excluded" variant comes later)
SMALL = 20                          # counts under this are written as "<20"
WEIGHT_COLUMNS = ["geo", "ref_year", "grouping", "group", "spending", "imputed_rent", "hh_weighting", "tutoring",
                  "coicop18",
                  "digits", "leaf", "share", "se", "rse", "high_rse", "n_households_unweighted", "reliability",
                  "se_design", "classification_native", "source_version"]
GROUP_COLUMNS = ["geo", "ref_year", "grouping", "group", "n_households", "households_weighted",
                 "people_weighted", "uncovered_purchases_share", "se_design", "se_note", "source_version"]
CODE_FILES = ("puf.py", "groups.py", "shares.py", "bootstrap.py", "mapping.py", "weights.py")
DATA_FILES = (mapping.V1_TO_2018, mapping.OLD_TO_V1, "hbs_puf_missing_items.toml")


def code_fingerprint() -> str:
    """sha256 over the code and data files that shape the result (there is no version control
    history to point at yet)."""
    # Line endings are normalised: a Windows checkout (CRLF) and a Linux one (LF) of the same code
    # must give the same fingerprint.
    h = hashlib.sha256()
    for name in CODE_FILES:
        h.update(resources.files("traceconomics.local").joinpath(name).read_bytes().replace(b"\r\n", b"\n"))
    for name in DATA_FILES:
        h.update(resources.files("traceconomics.data").joinpath(name).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def _count(n: int) -> str:
    return f"<{SMALL}" if n < SMALL else str(n)


def _num(x, digits: int = 10) -> str:
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{digits}g}"


def build(archive: Archive, year: int, replicates: int = bootstrap.REPLICATES) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(weights, groups, provenance) for one survey year."""
    rec = archive.latest(puf.SOURCE, puf.dataset(year))
    survey = puf.read(archive, year)
    groups = assign(survey)                       # on the survey as read: tenure needs its own rent codes
    mapped = mapping.to_2018(survey)              # same households, same totals, COICOP 2018 codes
    parts = []
    for spending in SPENDING:
        t = shares(mapped, groups, spending)
        design, se = bootstrap.standard_errors(mapped, groups, replicates=replicates, spending=spending)
        parts.append(bootstrap.with_errors(t, se, design).assign(spending=spending))
    t = pd.concat(parts, ignore_index=True)
    source_version = f"{puf.SOURCE}/{puf.dataset(year)}@{rec['sha256'][:12]}"

    weights = pd.DataFrame({
        "geo": GEO, "ref_year": year, "grouping": t.grouping, "group": t.group, "spending": t.spending,
        "imputed_rent": t.imputed_rent.map(IMPUTED_RENT), "hh_weighting": HH_WEIGHTING, "tutoring": TUTORING,
        "coicop18": t.code, "digits": t.digits, "leaf": t.leaf,
        "share": t.share, "se": t.se, "rse": t.rse, "high_rse": t.high_rse,
        "n_households_unweighted": t.n_reporting.map(_count), "reliability": t.reliability,
        "se_design": design.status, "classification_native": survey.classification, "source_version": source_version,
    })[WEIGHT_COLUMNS]

    tables = v2.archived_tables(archive)
    uncovered, gaps = v2.uncovered(survey, hbs_tables.parse(tables[year], year))
    people = groups.people_weight
    w = survey.households.weight
    group_rows = []
    for grouping, group, member in memberships(groups):
        group_rows.append({
            "geo": GEO, "ref_year": year, "grouping": grouping, "group": group,
            "n_households": _count(int(member.sum())),
            "households_weighted": float(w[member].sum()),
            "people_weighted": float(people[member].sum()),
            "uncovered_purchases_share": uncovered, "se_design": design.status, "se_note": design.note,
            "source_version": source_version,
        })
    group_table = pd.DataFrame(group_rows)[GROUP_COLUMNS]

    provenance = {
        "survey": source_version,
        "table_103": hashlib.sha256(tables[year].read_bytes()).hexdigest()[:12],
        "mapping": {name: hashlib.sha256(resources.files("traceconomics.data").joinpath(name).read_bytes()).hexdigest()[:12]
                    for name in (mapping.V1_TO_2018, mapping.OLD_TO_V1)},
        "code_version": __version__, "code_fingerprint": code_fingerprint()[:16],
        "replicates": replicates if design.status != "unavailable" else 0, "seed": bootstrap.SEED,
        "uncovered_items_eur_month": {c: round(g, 2) for c, g in gaps.items()},
    }
    return weights, group_table, provenance


def to_csv(table: pd.DataFrame, header: list[str]) -> bytes:
    out = io.StringIO()
    for line in header:
        out.write(f"# {line}\n")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(table.columns)
    for row in table.itertuples(index=False):
        w.writerow([_num(v) if isinstance(v, (float, np.floating)) else ("" if v is pd.NA or v is None else v)
                    for v in row])
    return out.getvalue().encode("utf-8")


def run(archive: Archive, years: list[int], replicates: int = bootstrap.REPLICATES) -> list[dict]:
    """Build and archive each year; return one line of report per year."""
    report = []
    for year in years:
        weights, group_table, provenance = build(archive, year, replicates)
        head = [f"Greek household budget survey {year}: spending shares by group and COICOP 2018 code.",
                "Built from the survey's public use file by Traceconomics; aggregates only. Counts under 20 are written as <20.",
                "provenance: " + json.dumps(provenance, ensure_ascii=False, sort_keys=True)]
        now = datetime.now(UTC)
        results = []
        for name, table in ((WEIGHTS, weights), (GROUPS, group_table)):
            dataset = name.format(year=year)
            r = archive.store_bytes(SOURCE, dataset, to_csv(table, head), url=None, retrieved_at=now, ext=".csv",
                                    kind="local", extra={"original_name": f"{dataset}.csv", "note": "built locally"})
            results.append(r.status)
        leaf = weights[weights.leaf & (weights.imputed_rent == "excluded") & (weights.spending == "purchases")
                       & weights.grouping.isin(PUBLISHED)]
        report.append({"year": year, "weights": results[0], "groups": results[1], "rows": len(weights),
                       "se_design": weights.se_design.iloc[0],
                       "uncovered": round(float(group_table.uncovered_purchases_share.iloc[0]), 4),
                       "leaves_suppressed": int((leaf.reliability == "suppressed").sum()),
                       "leaves": int(len(leaf))})
    return report
