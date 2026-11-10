"""Household weights calibrated to the census's tenure split: renters counted in full.

The household budget survey (HBS) finds about a third fewer renting households than the census
(16.8% of households in 2021 against the census's 24.5%), in every region and every household
type, and its weights are never adjusted for tenure. The likely cause is how non-response is
handled: a household that can't be interviewed is replaced by the next one on the list that can,
and renters are harder to find at home. With renters missing, rent weighs too little in every
basket that mixes tenures (all households, the income fifths, pensioners, household types).

So before any group is formed, each survey's household weights are scaled, one factor per tenure
class, so that renters (market and reduced rent), owners and households housed free make up the
target shares, with the total of households unchanged (post-stratification on one margin). The
target is EU-SILC's household split (ELSTAT's income survey, archived by `traceconomics silc run`
as `oet-local/silc-tenure-gr-YYYY`). EU-SILC fits its own weights to the census's tenure counts,
so its split is in effect the census's, carried forward to each year.

EU-SILC fits to the 2011 census until its 2022 survey and to the 2021 census from 2023, so its
renter share sits at 21.8% for a decade and then jumps to 24.5%. That jump is the change of the
ten years between the censuses, booked in one year. The target spreads it: for each survey year
from 2012 to 2022, EU-SILC's own split plus the part of the jump (EU-SILC 2023 minus 2022, per
tenure) that the years since the 2011 census make up, a tenth per year, all of it from 2021. Up to
2011 and from 2023 the target is EU-SILC's split as published.

What it is and isn't:
- Only the tenure margin is fitted. ELSTAT's own calibration (household size, people's sex and
  age) is disturbed a little; fixing the household-size mix alone moves renters by about 0.1
  points, so the disturbance is small.
- Scaling every renter by the same factor leaves the renters' own basket as it was (a group's
  shares are ratios within the group); the same for owners and the housed free. What changes is
  every group that mixes tenures, and which fifth some households fall in.
- The few households whose tenure can't be told (none or one or two a year) keep their weight,
  and the shares are of the households whose tenure is known.
- The comparisons with ELSTAT's own tables (spending by item, household types, rent paid) keep
  the survey's weights as published: they check our reading of ELSTAT's file, not our method.
- In the bootstrap, each replicate's weights are calibrated again, as survey practice does for
  calibrated weights, so the standard errors include the calibration.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from traceconomics.archive.store import Archive
from traceconomics.checks import FormatError, require
from traceconomics.local.puf import Survey
from traceconomics.sources import oet_local

SOURCE = "oet-local"
SILC = "silc-tenure-gr-{year}"
TENURES = ("renter", "owner", "rent_free")
SUM_TOLERANCE = 1e-9               # renters, owners and housed free make up all of EU-SILC's households
CENSUS = 2011                      # the census EU-SILC is fitted to until ...
LAST_ON_OLD = 2022                 # ... its 2022 survey
FIRST_ON_NEW = 2023                # the first EU-SILC survey fitted to the next census (2021)
NEXT_CENSUS = 2021


@dataclass(frozen=True)
class Target:
    """One survey year's target: tenure -> share of households, and how it was set."""
    shares: dict[str, float]
    basis: str
    silc: dict[str, float]           # EU-SILC's own split for the year
    sources: tuple[str, ...]         # the archived EU-SILC tables used, with their hashes


def _silc_table(archive: Archive, year: int) -> tuple[dict[str, float], str]:
    """({tenure: share of households}, "dataset@hash") from the archived EU-SILC table."""
    dataset = SILC.format(year=year)
    rec = archive.latest(SOURCE, dataset)
    if rec is None:
        raise FormatError(f"no EU-SILC tenure table for {year}: run `traceconomics silc run` first")
    households = {}
    for geo, tenure, measure, _period, _text, value in oet_local.rows(archive.root / rec["path"], "oet-silc-tenure"):
        if geo == "GR" and measure == "households_weighted":
            households[tenure] = value
    missing = [t for t in ("all", *TENURES) if households.get(t) is None]
    if missing or not households["all"] > 0:
        raise FormatError(f"EU-SILC {year}: no households for {missing or ['all']}")
    shares = {t: households[t] / households["all"] for t in TENURES}
    if abs(sum(shares.values()) - 1) > SUM_TOLERANCE:
        raise FormatError(f"EU-SILC {year}: renters, owners and housed free add up to {sum(shares.values()):.6f} of households")
    return shares, f"{SOURCE}/{dataset}@{rec['sha256'][:12]}"


def census_part(year: int) -> float:
    """How much of the step between the censuses a survey year carries: 0 up to 2011, a tenth
    more each year, all of it from 2021."""
    return min(max((year - CENSUS) / (NEXT_CENSUS - CENSUS), 0.0), 1.0)


def target(archive: Archive, year: int) -> Target:
    silc, source = _silc_table(archive, year)
    if year <= CENSUS or year >= FIRST_ON_NEW:
        return Target(silc, "EU-SILC's split for the year", silc, (source,))
    old, old_source = _silc_table(archive, LAST_ON_OLD)
    new, new_source = _silc_table(archive, FIRST_ON_NEW)
    part = census_part(year)
    shares = {t: silc[t] + part * (new[t] - old[t]) for t in TENURES}
    require(all(s > 0 for s in shares.values()), f"{year}: a tenure's target share is not positive: {shares}")
    return Target(shares, f"EU-SILC's split for the year plus {part:.1f} of its step from {LAST_ON_OLD} to "
                          f"{FIRST_ON_NEW} (the change between the {CENSUS} and {NEXT_CENSUS} censuses)",
                  silc, tuple(sorted({source, old_source, new_source})))


def member(tenure: pd.Series, label: str) -> np.ndarray:
    return (pd.Series(tenure) == label).fillna(False).to_numpy(bool)


def calibrate(weights: np.ndarray, tenure: pd.Series, shares: dict[str, float]) -> np.ndarray:
    """The weights (households, or households x replicates) scaled within each tenure class so the
    classes make up `shares` of the households whose tenure is known, column by column; households
    with no tenure keep their weight."""
    w = np.asarray(weights, dtype=float)
    flat = w.ndim == 1
    w = w.reshape(len(w), -1)
    members = {t: member(tenure, t) for t in TENURES}
    known = np.logical_or.reduce(list(members.values()))
    total = w[known].sum(axis=0)
    out = w.copy()
    for t, m in members.items():
        if shares[t] == 0 and not m.any():
            continue                 # a class the target leaves out and the survey has none of
        current = w[m].sum(axis=0)
        require(bool((current > 0).all()), f"no weighted households with tenure {t}")
        out[m] = w[m] * (shares[t] * total / current)
    return out[:, 0] if flat else out


def calibrated(survey: Survey, tenure: pd.Series, t: Target) -> tuple[Survey, dict[str, float]]:
    """(the survey with calibrated household weights, each tenure's weight factor)."""
    w = survey.households.weight.to_numpy(float)
    new = calibrate(w, tenure, t.shares)
    factors = {}
    for label in TENURES:
        m = member(tenure, label)
        factors[label] = float(new[m].sum() / w[m].sum()) if m.any() else 1.0
    return replace(survey, households=survey.households.assign(weight=new)), factors
