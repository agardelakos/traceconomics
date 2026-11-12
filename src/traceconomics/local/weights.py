"""The whole run for one survey year: archived microdata -> weights table -> archive (source `oet-local`).

Per year, six CSV files, each opened by `#` lines with their provenance:

- `hbs-weights-gr-YYYY`: one row per spending concept, grouping, group, imputed-rent option and
  COICOP 2018 code:
  the share of the group's spending, its standard error, how many sampled households reported
  spending on it, and the publication tier;
- `hbs-groups-gr-YYYY`: one row per grouping and group: sample size, weighted households and
  people, and the year's facts (the part of purchases the microdata leave out, the
  standard-error design);
- `hbs-limits-gr-YYYY`: the income limits between the default grouping's fifths (B: people
  ranked by equivalised money income), one row per fifth with an upper limit: the limit in euros
  a year per adult equivalent, rounded to the euro, and its standard error. A limit is the
  midpoint between the two households either side of it (`groups.cut_points`), so it is never one
  household's income alone (two households that report the same income share it);
- `hbs-hhtypes-gr-YYYY`: our household types next to ELSTAT's own (`HB074`): each type's household
  count and weighted share by both, and how many households the two place alike. Kept as a
  record for comparing our figures with the official ones; the consistency topic (module5)
  publishes it, module1 doesn't read it. If fewer
  than 90% of households agree, the run stops for a look (our bug or theirs), unless the year is
  a known case (`ELSTAT_TYPE_UNUSABLE`).
- `hbs-rent-gr-YYYY`: rent paid, by tenure (renters, owners, housed free, and all households):
  households counted and weighted, people weighted, and the rent households pay for their main
  home in euros a year (the weighted sum of code 0411, all modes, as the survey records it). For
  the consistency topic, which lines the survey's rent up against the census, EU-SILC and the
  national accounts; module1 doesn't read it.
- `hbs-spending-gr-YYYY`: our reading of the survey file against ELSTAT's published spending
  table (table 1.03, average monthly purchases by item), the V2 check: per column (all
  households, and each band where the year's bands can be rebuilt) and item, ELSTAT's figure,
  ours, and whether they match to the cent, differ, or are excused (an item the public file lacks
  or cuts, `data/hbs_puf_missing_items.toml`); one row per column gives both household totals.
  For the consistency topic, which publishes it; module1 doesn't read it.

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
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources

import numpy as np
import pandas as pd

from traceconomics import __version__
from traceconomics.archive.store import Archive
from traceconomics.checks import require
from traceconomics.local import bootstrap, calibration, mapping, puf, v2
from traceconomics.local.groups import ELSTAT_TYPES, RANKED, assign, cut_points, ranking
from traceconomics.module1.index import HOUSEHOLD_TYPES
from traceconomics.module1.schedule import UNUSABLE_INCOMES, unusable
from traceconomics.local.shares import PUBLISHED, SPENDING, memberships, shares
from traceconomics.sources.elstat import hbs_tables

SOURCE = "oet-local"
GEO = "GR"
WEIGHTS = "hbs-weights-gr-{year}"
GROUPS = "hbs-groups-gr-{year}"
LIMITS = "hbs-limits-gr-{year}"
LIMITS_GROUPING = "B"  # the default grouping, the one the site describes in euros
LIMIT_UNIT = "EUR_PER_ADULT_EQ_Y"  # money income after taxes, a year, divided by the modified OECD scale
IMPUTED_RENT = {1: "excluded", 2: "included"}
HH_WEIGHTING = "plutocratic"  # each household counts in proportion to what it spends
TUTORING = "priced"  # tutoring stays in the basket (the "excluded" variant comes later)
SMALL = 20  # counts under this are written as "<20"
WEIGHT_COLUMNS = [
    "geo",
    "ref_year",
    "grouping",
    "group",
    "spending",
    "imputed_rent",
    "hh_weighting",
    "tutoring",
    "coicop18",
    "digits",
    "leaf",
    "share",
    "se",
    "rse",
    "high_rse",
    "n_households_unweighted",
    "reliability",
    "se_design",
    "classification_native",
    "source_version",
]
GROUP_COLUMNS = [
    "geo",
    "ref_year",
    "grouping",
    "group",
    "n_households",
    "households_weighted",
    "people_weighted",
    "uncovered_purchases_share",
    "se_design",
    "se_note",
    "source_version",
]
TYPES = "hbs-hhtypes-gr-{year}"
TYPE_COLUMNS = [
    "geo",
    "ref_year",
    "group",
    "n_households",
    "share_households",
    "elstat_n_households",
    "elstat_share_households",
    "agreement",
    "elstat_status",
    "source_version",
]
TYPE_AGREEMENT = 0.90  # an assumption: the lowest seen in 2008-2024 (2023 aside) is 95.2%
# Years whose ELSTAT type can't be compared, and why (checked 2026-11-05).
ELSTAT_TYPE_UNUSABLE = {
    2023: "HB074 doesn't match the households' own sizes: 34% of its one-adult households have one member"
}
RENT = "hbs-rent-gr-{year}"
RENT_COLUMNS = [
    "geo",
    "ref_year",
    "tenure",
    "n_households",
    "households_weighted",
    "people_weighted",
    "rent_paid_eur",
    "source_version",
]
SPENDING_CHECK = "hbs-spending-gr-{year}"
SPENDING_COLUMNS = ["geo", "ref_year", "group", "coicop", "item", "published", "ours", "result", "source_version"]
HOUSEHOLDS = "households"  # the `coicop` of each column's row of household totals
RENT_CODE = "0411"  # actual rent for the main home, the code the tenure rule reads
LIMIT_COLUMNS = ["geo", "ref_year", "grouping", "group", "unit", "limit", "se", "se_design", "source_version"]
CODE_FILES = ("puf.py", "groups.py", "shares.py", "bootstrap.py", "calibration.py", "mapping.py", "weights.py", "v2.py")
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


@dataclass(frozen=True)
class Prepared:
    """One survey ready for the groups' shares: as read, and with its weights calibrated."""

    survey: puf.Survey  # as read: ELSTAT's weights
    as_read: pd.DataFrame  # its groups on ELSTAT's weights (tenure needs its own rent codes)
    calibrated: puf.Survey  # weights calibrated to the target tenure split (`calibration`)
    groups: pd.DataFrame  # the groups formed on the calibrated weights
    mapped: puf.Survey  # the calibrated survey in COICOP 2018 codes (same households, same totals)
    target: calibration.Target
    factors: dict[str, float]  # each tenure's weight factor

    def recalibrate(self, w: np.ndarray) -> np.ndarray:
        """The same calibration applied to other weights (bootstrap replicates)."""
        return calibration.calibrate(w, self.groups["tenure"], self.target.shares)


def prepare(archive: Archive, year: int) -> Prepared:
    survey = puf.read(archive, year)
    as_read = assign(survey)
    target = calibration.target(archive, year)
    calibrated, factors = calibration.calibrated(survey, as_read["tenure"], target)
    groups = assign(calibrated)
    return Prepared(survey, as_read, calibrated, groups, mapping.to_2018(calibrated), target, factors)


def build(
    archive: Archive, year: int, replicates: int = bootstrap.REPLICATES
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """(weights, groups, limits, household types, rent, spending check, provenance) for one survey year."""
    rec = archive.latest(puf.SOURCE, puf.dataset(year))
    p = prepare(archive, year)
    survey, as_read, calibrated, groups, mapped, target, factors = (
        p.survey,
        p.as_read,
        p.calibrated,
        p.groups,
        p.mapped,
        p.target,
        p.factors,
    )
    recalibrate = p.recalibrate

    parts = []
    for spending in SPENDING:
        t = shares(mapped, groups, spending)
        design, se = bootstrap.standard_errors(
            mapped, groups, replicates=replicates, spending=spending, calibrate=recalibrate
        )
        parts.append(bootstrap.with_errors(t, se, design).assign(spending=spending))
    t = pd.concat(parts, ignore_index=True)
    t = t[[not unusable(g, year) for g in t.grouping]]
    source_version = f"{puf.SOURCE}/{puf.dataset(year)}@{rec['sha256'][:12]}"

    weights = pd.DataFrame(
        {
            "geo": GEO,
            "ref_year": year,
            "grouping": t.grouping,
            "group": t.group,
            "spending": t.spending,
            "imputed_rent": t.imputed_rent.map(IMPUTED_RENT),
            "hh_weighting": HH_WEIGHTING,
            "tutoring": TUTORING,
            "coicop18": t.code,
            "digits": t.digits,
            "leaf": t.leaf,
            "share": t.share,
            "se": t.se,
            "rse": t.rse,
            "high_rse": t.high_rse,
            "n_households_unweighted": t.n_reporting.map(_count),
            "reliability": t.reliability,
            "se_design": design.status,
            "classification_native": survey.classification,
            "source_version": source_version,
        }
    )[WEIGHT_COLUMNS]

    tables = v2.archived_tables(archive)
    table_103 = hbs_tables.parse(tables[year], year)
    uncovered, gaps = v2.uncovered(survey, table_103)
    people = groups.people_weight
    w = calibrated.households.weight
    group_rows = []
    for grouping, group, member in memberships(groups):
        if unusable(grouping, year):
            continue
        group_rows.append(
            {
                "geo": GEO,
                "ref_year": year,
                "grouping": grouping,
                "group": group,
                "n_households": _count(int(member.sum())),
                "households_weighted": float(w[member].sum()),
                "people_weighted": float(people[member].sum()),
                "uncovered_purchases_share": uncovered,
                "se_design": design.status,
                "se_note": design.note,
                "source_version": source_version,
            }
        )
    group_table = pd.DataFrame(group_rows)[GROUP_COLUMNS]
    limits = limits_table(calibrated, year, replicates, source_version, recalibrate)
    # The comparisons with ELSTAT's own tables and the census keep ELSTAT's weights: they check
    # our reading of its file, and the survey's renter shortfall is what they show.
    types = types_table(survey, as_read, year, source_version)
    rent = rent_table(survey, as_read, year, source_version)
    spending_check = spending_table(v2.compare_all(survey, table_103), year, source_version)

    provenance = {
        "survey": source_version,
        "table_103": hashlib.sha256(tables[year].read_bytes()).hexdigest()[:12],
        "mapping": {
            name: hashlib.sha256(resources.files("traceconomics.data").joinpath(name).read_bytes()).hexdigest()[:12]
            for name in (mapping.V1_TO_2018, mapping.OLD_TO_V1)
        },
        "code_version": __version__,
        "code_fingerprint": code_fingerprint()[:16],
        "replicates": replicates if design.status != "unavailable" else 0,
        "seed": bootstrap.SEED,
        "uncovered_items_eur_month": {c: round(g, 2) for c, g in gaps.items()},
        "tenure_target": {
            "shares": {k: round(v, 6) for k, v in target.shares.items()},
            "basis": target.basis,
            "silc": list(target.sources),
        },
        "tenure_factors": {k: round(v, 6) for k, v in factors.items()},
    }
    if unusable(LIMITS_GROUPING, year):
        provenance["income_groups"] = (
            f"not built: survey {year}'s incomes can't rank households; "
            f"survey {UNUSABLE_INCOMES[year]} stands in for it"
        )
    return weights, group_table, limits, types, rent, spending_check, provenance


def types_table(survey: puf.Survey, groups: pd.DataFrame, year: int, source_version: str) -> pd.DataFrame:
    """Our household types next to ELSTAT's own; refuses a year where they agree on fewer than
    TYPE_AGREEMENT of households, unless it is a known case."""
    h = survey.households
    ours = groups["hhtype"]
    theirs = (
        pd.Series(h["elstat_type"].map(ELSTAT_TYPES).to_numpy(), dtype="string")
        if "elstat_type" in h
        else pd.Series(pd.NA, index=h.index, dtype="string")
    )
    agreement = float((ours == theirs).fillna(False).mean())
    known = ELSTAT_TYPE_UNUSABLE.get(year)
    require(
        known is not None or agreement >= TYPE_AGREEMENT,
        f"{year}: our household types agree with ELSTAT's on {agreement:.1%} of households, under "
        f"{TYPE_AGREEMENT:.0%}: look before going on (our bug or a change in their file)",
    )
    w = h.weight.to_numpy(float)
    total = w.sum()
    rows = []
    for t in HOUSEHOLD_TYPES:
        mine, theirs_t = (ours == t).fillna(False).to_numpy(bool), (theirs == t).fillna(False).to_numpy(bool)
        rows.append(
            {
                "geo": GEO,
                "ref_year": year,
                "group": t,
                "n_households": _count(int(mine.sum())),
                "share_households": float(w[mine].sum() / total),
                "elstat_n_households": _count(int(theirs_t.sum())),
                "elstat_share_households": float(w[theirs_t].sum() / total),
                "agreement": agreement,
                "elstat_status": f"unusable: {known}" if known else "compared",
                "source_version": source_version,
            }
        )
    return pd.DataFrame(rows)[TYPE_COLUMNS]


def rent_table(survey: puf.Survey, groups: pd.DataFrame, year: int, source_version: str) -> pd.DataFrame:
    """Rent paid for the main home, by tenure and for all households: counts, weighted households
    and people, and the yearly total in euros. Spending is held in annual euros (`puf`), so the
    total is the weighted sum of the rent column. Owners and the housed free pay none by
    definition (tenure is decided by that same column first), and their rows say so."""
    w = survey.households.weight.to_numpy(float)
    rent = survey.spending[RENT_CODE].fillna(0).to_numpy(float)
    people = groups.people_weight.to_numpy(float)
    rows = []
    tenure = groups["tenure"]
    for label in ("all", "owner", "renter", "rent_free"):
        member = np.ones(len(w), bool) if label == "all" else (tenure == label).fillna(False).to_numpy(bool)
        rows.append(
            {
                "geo": GEO,
                "ref_year": year,
                "tenure": label,
                "n_households": _count(int(member.sum())),
                "households_weighted": float(w[member].sum()),
                "people_weighted": float(people[member].sum()),
                "rent_paid_eur": float((w * rent)[member].sum()),
                "source_version": source_version,
            }
        )
    return pd.DataFrame(rows)[RENT_COLUMNS]


def spending_table(results: list[v2.V2Result], year: int, source_version: str) -> pd.DataFrame:
    """V2's comparison as a table: per column, a row of household totals (ELSTAT's against the
    survey file's weights), then every item compared, with its result. Only averages over all
    households or a published band, and ELSTAT's own figures, so nothing here is one household's."""
    rows = []
    for r in results:
        rows.append(
            {
                "geo": GEO,
                "ref_year": year,
                "group": r.group,
                "coicop": HOUSEHOLDS,
                "item": "",
                "published": r.households_published,
                "ours": r.households_puf,
                "result": "matched" if r.same_households else "differs",
                "source_version": source_version,
            }
        )
        for code, label, published, ours, result in r.rows:
            rows.append(
                {
                    "geo": GEO,
                    "ref_year": year,
                    "group": r.group,
                    "coicop": code,
                    "item": label,
                    "published": published,
                    "ours": np.nan if ours is None else ours,
                    "result": result,
                    "source_version": source_version,
                }
            )
    return pd.DataFrame(rows)[SPENDING_COLUMNS]


def limits_table(
    survey: puf.Survey, year: int, replicates: int, source_version: str, calibrate: bootstrap.Calibrate | None = None
) -> pd.DataFrame:
    """The limits between the default grouping's parts, rounded to the euro (half to even), with
    standard errors from the same bootstrap as the shares. For a survey whose incomes can't
    rank households: no rows (the file is still written, so the store withdraws earlier limits)."""
    if unusable(LIMITS_GROUPING, year):
        return pd.DataFrame(columns=LIMIT_COLUMNS)
    value, by_people, parts, prefix = RANKED[LIMITS_GROUPING]
    values, size = ranking(survey)
    w = survey.households.weight.to_numpy(float)
    basis = w * np.nan_to_num(size.to_numpy(float)) if by_people else w
    point = cut_points(values[value], basis, survey.households.hh, parts)[:, 0]
    require(not np.isnan(point).any(), f"{year}: an income part is empty")
    design, se = (
        bootstrap.limit_errors(survey, LIMITS_GROUPING, replicates, calibrate=calibrate)
        if replicates
        else (bootstrap.design(survey), None)
    )
    return pd.DataFrame(
        {
            "geo": GEO,
            "ref_year": year,
            "grouping": LIMITS_GROUPING,
            "group": [f"{prefix}{k}" for k in range(1, parts)],
            "unit": LIMIT_UNIT,
            "limit": [int(round(float(x))) for x in point],
            "se": se if se is not None else np.nan,
            "se_design": design.status,
            "source_version": source_version,
        }
    )[LIMIT_COLUMNS]


def to_csv(table: pd.DataFrame, header: list[str]) -> bytes:
    out = io.StringIO()
    for line in header:
        out.write(f"# {line}\n")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(table.columns)
    for row in table.itertuples(index=False):
        w.writerow(
            [_num(v) if isinstance(v, (float, np.floating)) else ("" if v is pd.NA or v is None else v) for v in row]
        )
    return out.getvalue().encode("utf-8")


def run(archive: Archive, years: list[int], replicates: int = bootstrap.REPLICATES) -> list[dict]:
    """Build and archive each year; return one line of report per year."""
    report = []
    for year in years:
        weights, group_table, limits, types, rent, spending_check, provenance = build(archive, year, replicates)
        head = [
            f"Greek household budget survey {year}: spending shares by group and COICOP 2018 code.",
            "Built from the survey's public use file by Traceconomics; aggregates only. Counts under 20 are written as <20.",
            "provenance: " + json.dumps(provenance, ensure_ascii=False, sort_keys=True),
        ]
        now = datetime.now(UTC)
        results = []
        for name, table in (
            (WEIGHTS, weights),
            (GROUPS, group_table),
            (LIMITS, limits),
            (TYPES, types),
            (RENT, rent),
            (SPENDING_CHECK, spending_check),
        ):
            dataset = name.format(year=year)
            lines = head
            if name == LIMITS and table.empty:
                lines = [
                    f"Greek household budget survey {year}: no income limits: the survey's incomes can't "
                    "rank households.",
                    *head[1:],
                ]
            elif name == LIMITS:
                lines = [
                    f"Greek household budget survey {year}: the income limits between the fifths of people "
                    "ranked by equivalised money income (midpoints, rounded to the euro).",
                    *head[1:],
                ]
            elif name == TYPES:
                lines = [
                    f"Greek household budget survey {year}: our household types next to ELSTAT's own (HB074).",
                    *head[1:],
                ]
            elif name == RENT:
                lines = [
                    f"Greek household budget survey {year}: rent paid for the main home, by tenure, euros a year.",
                    *head[1:],
                ]
            elif name == SPENDING_CHECK:
                lines = [
                    f"Greek household budget survey {year}: our reading of the public use file against ELSTAT's "
                    "table 1.03 (average monthly purchases, euros), item by item.",
                    *head[1:],
                ]
            r = archive.store_bytes(
                SOURCE,
                dataset,
                to_csv(table, lines),
                url=None,
                retrieved_at=now,
                ext=".csv",
                kind="local",
                extra={"original_name": f"{dataset}.csv", "note": "built locally"},
            )
            results.append(r.status)
        leaf = weights[
            weights.leaf
            & (weights.imputed_rent == "excluded")
            & (weights.spending == "purchases")
            & weights.grouping.isin(PUBLISHED)
        ]
        report.append(
            {
                "year": year,
                "weights": results[0],
                "groups": results[1],
                "limits": results[2],
                "types": results[3],
                "types_agreement": round(float(types.agreement.iloc[0]), 4),
                "rent": results[4],
                "spending_check": results[5],
                "spending_differs": int((spending_check.result == "differs").sum()),
                "rent_paid_eur": int(round(float(rent.set_index("tenure").loc["all", "rent_paid_eur"]))),
                "limits_eur": [int(x) for x in limits["limit"]],
                "rows": len(weights),
                "tenure_factors": provenance["tenure_factors"],
                "se_design": weights.se_design.iloc[0],
                "uncovered": round(float(group_table.uncovered_purchases_share.iloc[0]), 4),
                "leaves_suppressed": int((leaf.reliability == "suppressed").sum()),
                "leaves": int(len(leaf)),
            }
        )
    return report
