"""Checks of the mapping to COICOP 2018: a year mapped against the next year in the new codes.

No survey was published in both classifications, so the test compares neighbours: the last year
in the old codes, mapped, against the first year in the new ones (2023 -> 2024), and the last
year of the older national list, bridged, against the first year in ECOICOP v1 (2014 -> 2015,
both mapped). All households, without imputed rent, at division and group level.

A year apart, shares move anyway. A difference is flagged only when it is
- larger than 0.2 percentage points (MIN_PP),
- more than three times the code's usual year-to-year change (the median over the mapped
  2016-2023 series), and
- beyond sampling noise: more than twice the two years' combined bootstrap standard error.

A flagged difference can come from the mapping only if a fair part of the code's spending was
decided by a split across its boundary (`exposure`). Below EXPOSURE it is reported as "not from the mapping"
(a real change, or the statistical office filing things differently, such as tutoring moving to
10.5 in 2024). Above it, the code must be explained in `data/mapping_explained.toml`, or the
check fails.

A second, report-only comparison sets each year's mapped shares against ELSTAT's own CPI weights
re-issued in COICOP 2018 (table 07): those come from the same surveys, but are price-updated and
lag them, so they can't be held to a tolerance.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from importlib import resources

import numpy as np
import pandas as pd

from traceconomics.local import bootstrap, mapping, puf
from traceconomics.local.groups import assign
from traceconomics.local.shares import shares

MIN_PP = 0.2
TIMES_USUAL = 3
NOISE_SE = 2
EXPOSURE = 0.10
BASELINE_YEARS = range(2016, 2024)
REPLICATES = 500        # enough for a noise threshold


@dataclass
class Flag:
    code: str
    older: float            # share %, the older year mapped
    newer: float
    usual: float            # median year-to-year change, pp
    noise: float            # NOISE_SE x combined standard error, pp
    exposure: float         # part of the older year's spending in this code that a split decided
    explanation: str = ""

    @property
    def from_mapping(self) -> bool:
        return self.exposure >= EXPOSURE


@dataclass
class Comparison:
    older_year: int
    newer_year: int
    table: pd.DataFrame                         # code, older, newer, diff (all in %)
    flags: list[Flag] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(f.explanation or not f.from_mapping for f in self.flags)


def explained() -> dict[str, dict[str, str]]:
    """{"2023-2024": {code: reason}} from the package data file."""
    data = tomllib.loads(resources.files("traceconomics.data").joinpath("mapping_explained.toml").read_text(encoding="utf-8"))
    return {k: {c: e["reason"] for c, e in v.items()} for k, v in data.items()}


def all_households(survey, replicates: int = 0) -> pd.DataFrame:
    """code -> share and se (%), all households, option 1, divisions and groups."""
    groups = assign(survey)
    t = shares(survey, groups)
    if replicates:
        d, se = bootstrap.standard_errors(survey, groups, replicates=replicates)
        t = bootstrap.with_errors(t, se, d)
    else:
        t["se"] = np.nan
    t = t[(t.grouping == "all") & (t.imputed_rent == 1) & t.digits.isin([2, 3])]
    return t.set_index("code")[["share", "se"]] * 100


def effective_table(year: int) -> pd.DataFrame:
    """The survey's own codes -> COICOP 2018: from_code, to_code, share (the older list goes through
    the bridge and the v1 table in one step)."""
    v1 = mapping.load(mapping.V1_TO_2018)[["from_code", "to_code", "share"]]
    if year not in mapping.OLD_LIST_YEARS:
        return v1
    old = mapping.load(mapping.OLD_TO_V1)[["from_code", "to_code", "share"]]
    both = old.merge(v1, left_on="to_code", right_on="from_code", suffixes=("", "_v1"))
    both["share"] = both.share * both.share_v1
    return (both.groupby(["from_code", "to_code_v1"], as_index=False).share.sum()
            .rename(columns={"to_code_v1": "to_code"}))


def exposure(survey, table: pd.DataFrame | None = None) -> pd.Series:
    """Per COICOP 2018 division and group: the part of its mapped spending that a split decided.

    A source whose split sends a share p into the code and 1 - p elsewhere could, with other
    splitting weights, have sent anything from 0 to all of itself there; the amount at stake is
    taken as min(p, 1 - p) of the source's spending. Splits inside the code don't count."""
    table = effective_table(survey.year) if table is None else table
    w = survey.households.weight
    spend = {c: float((survey.spending[c] * w).sum()) for c in table.from_code.unique() if c in survey.spending}
    table = table[table.from_code.isin(spend)].assign(eur=lambda t: t.from_code.map(spend) * t.share)
    out = {}
    for k in (2, 3):
        t = table.assign(code=table.to_code.str[:k])
        into = t.groupby(["from_code", "code"], as_index=False).share.sum()
        into["at_stake"] = into.from_code.map(spend) * np.minimum(into.share, 1 - into.share)
        total = t.groupby("code").eur.sum()
        at_stake = into.groupby("code").at_stake.sum().reindex(total.index, fill_value=0.0)
        out.update((at_stake / total.where(total > 0)).fillna(0.0).to_dict())
    return pd.Series(out)


def compare(archive, older_year: int, newer_year: int, usual: pd.Series,
            reasons: dict[str, str] | None = None, replicates: int = REPLICATES) -> Comparison:
    older_survey = puf.read(archive, older_year)
    older = all_households(mapping.to_2018(older_survey), replicates)
    newer = all_households(mapping.to_2018(puf.read(archive, newer_year)), replicates)
    table = pd.DataFrame({"older": older.share, "newer": newer.share}).fillna(0.0)
    table["diff"] = table.newer - table.older
    exp = exposure(older_survey)
    result = Comparison(older_year, newer_year, table)
    reasons = reasons or {}
    for code, row in table.iterrows():
        noise = NOISE_SE * float(np.hypot(older.se.get(code, 0.0), newer.se.get(code, 0.0)))
        typical = float(usual.get(code, 0.0))
        if abs(row["diff"]) > MIN_PP and abs(row["diff"]) > TIMES_USUAL * typical and abs(row["diff"]) > noise:
            result.flags.append(Flag(code, row.older, row.newer, typical, noise, float(exp.get(code, 0.0)),
                                     reasons.get(code, "")))
    return result


def usual_change(archive) -> pd.Series:
    """Median absolute year-to-year change per code (pp), over the mapped 2016-2023 surveys."""
    series = {y: all_households(mapping.to_2018(puf.read(archive, y))).share for y in BASELINE_YEARS}
    years = list(BASELINE_YEARS)
    return pd.concat([(series[b] - series[a]).abs() for a, b in zip(years, years[1:])], axis=1).median(axis=1)


def cpi_report(archive, con, lags=(1, 2)) -> pd.DataFrame:
    """Mean absolute difference (per mille) per division between ELSTAT's CPI weights of year t
    (table 07, COICOP 2018) and our mapped all-households shares of survey t - lag."""
    from traceconomics.store.query import as_of

    cpi = as_of(con, "elstat:cpi07", where="unit = 'PM'").df()
    cpi = cpi[cpi.coicop18.fillna("").str.fullmatch(r"\d{2}")]
    ours = {}
    rows = []
    for year in sorted(int(y) for y in cpi.ref_period.unique()):
        row = {"cpi_year": year}
        for lag in lags:
            hbs = year - lag
            if hbs < 2008 or hbs > 2024:
                continue
            if hbs not in ours:
                ours[hbs] = all_households(mapping.to_2018(puf.read(archive, hbs))).share
            w = cpi[cpi.ref_period == str(year)].set_index("coicop18").value
            o = ours[hbs][ours[hbs].index.str.len() == 2] * 10
            both = pd.concat([w, o], axis=1, keys=["cpi", "ours"]).dropna()
            row[f"survey t-{lag}"] = round(float((both.cpi - both.ours).abs().mean()), 2)
        rows.append(row)
    return pd.DataFrame(rows)
