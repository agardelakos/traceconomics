"""Assign each surveyed household to its groups.

Groupings:

    A   households ranked by net money income, 20% of households per quintile
    B   people ranked by equivalised net money income, 20% of people per quintile (the default)
    C   people ranked by equivalised total spending, 20% of people per quintile
    tenure      renter, owner, or rent-free/subsidised (from the rent columns)
    pensioners  households whose main income source is a pension
    hhtype      who lives in the household, Eurostat's six household-budget-survey types:
                A1 one adult, A2 two adults, A_GE3 three or more adults, and the same with
                dependent children (A1_DCH, A2_DCH, A_GE3_DCH)
    all         every household

A household that can't be placed in a grouping (no person records, no rent of
any kind, no main income source) is left out of that grouping only; it still
counts in "all" and in the others.

Income is money income after taxes, without income in kind or imputed rent
(Eurostat's definition of disposable income; KEPE ranks the same way).
Equivalising uses the modified OECD scale: 1 for the first person aged 14 or
over, 0.5 for each other person aged 14 or over, 0.3 for each child under 14.

A dependent child, for the household types, follows Eurostat's written rule for the survey: anyone
under 16, or aged 16 to 24, a child of the reference person or spouse (relationship code 3), and
neither working nor unemployed (activity not 1 or 2). Everyone else is an adult. The files carry
ELSTAT's own type too (`elstat_type`), but it is only compared with ours, never used: in the 2023
file it doesn't match the households' own sizes. Note the two age limits: the size scale counts
children under 14, the types count dependent children under 16 (or students up to 24).

In a "people" quintile every member shares the household's equivalised
value, so a household falls wholly in one quintile. The cut points are set on
people (household weight x household size). A household that straddles a
cut point goes to the quintile holding the middle of its weight; ties in the
ranking value are broken by household identifier, so the result is
reproducible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from traceconomics.local.puf import Survey
from traceconomics.module1.index import HOUSEHOLD_TYPES  # noqa: F401  (the groups `household_type` gives)

PENSION = "4"   # HI11: main income source "Pensions, retirement benefits" (every year's codebook)


def household_size(survey: Survey) -> pd.DataFrame:
    """hh -> size and modified-OECD scale. Households without person records get NaN."""
    p = survey.persons
    g = p.assign(adult=p.age >= 14, child=p.age < 14).groupby("hh").agg(adults=("adult", "sum"), children=("child", "sum"))
    g["size"] = g.adults + g.children
    # 1 for the first adult; with no adult at all (not seen in the data), the first child counts 1.
    g["scale"] = np.where(g.adults > 0,
                          1 + 0.5 * (g.adults - 1) + 0.3 * g.children,
                          1 + 0.3 * (g.children - 1))
    return survey.households[["hh"]].join(g, on="hh").set_index("hh")[["size", "scale"]]


def quintile_matrix(value: pd.Series, weights: np.ndarray, ids: pd.Series, parts: int = 5) -> np.ndarray:
    """Quintile 1-5 (or 1..parts: deciles with parts=10) per row and per column of weights (n rows x
    R sets of weights, e.g. bootstrap replicates); 0 where the value is missing. The ranking is the
    same for every column, only the cut points move. A row with zero weight in a column gets a
    group there, but adds nothing to it."""
    weights = np.asarray(weights, dtype=float).reshape(len(value), -1)
    ok = value.notna().to_numpy()
    ranked = pd.DataFrame({"v": value.to_numpy()[ok], "id": ids.to_numpy()[ok], "row": np.flatnonzero(ok)})
    order = ranked.sort_values(["v", "id"], kind="mergesort").row.to_numpy()
    w = weights[order]
    middle = (np.cumsum(w, axis=0) - w / 2) / w.sum(axis=0)
    out = np.zeros(weights.shape, dtype=np.int8)
    out[order] = np.minimum((middle * parts).astype(int) + 1, parts)
    return out


def cut_points(value: pd.Series, weights: np.ndarray, ids: pd.Series, parts: int = 5) -> np.ndarray:
    """(parts - 1) x R: where each part ends, per column of weights, in the units of `value`.

    The limit between part k and part k + 1 is the midpoint of the last household ranked in part k
    and the first ranked in part k + 1, in the same order and with the same parts as
    `quintile_matrix`. The limits are published, so they are never one household's figure alone:
    either between two households' values, or, when the two report the same, a value both share. A row with zero weight in a column (a household not drawn in a bootstrap
    replicate) is skipped in that column. NaN where a part is empty."""
    weights = np.asarray(weights, dtype=float).reshape(len(value), -1)
    q = quintile_matrix(value, weights, ids, parts)
    ok = value.notna().to_numpy()
    ranked = pd.DataFrame({"v": value.to_numpy()[ok], "id": ids.to_numpy()[ok], "row": np.flatnonzero(ok)})
    order = ranked.sort_values(["v", "id"], kind="mergesort").row.to_numpy()
    v = value.to_numpy(dtype=float)[order]
    out = np.full((parts - 1, weights.shape[1]), np.nan)
    for j in range(weights.shape[1]):
        kept = weights[order, j] > 0
        qj, vj = q[order, j][kept], v[kept]
        for k in range(1, parts):
            below, above = np.flatnonzero(qj == k), np.flatnonzero(qj == k + 1)
            if len(below) and len(above):
                out[k - 1, j] = (vj[below[-1]] + vj[above[0]]) / 2
    return out


def quintiles(value: pd.Series, weight: pd.Series, ids: pd.Series, parts: int = 5) -> pd.Series:
    """Quintile 1-5 (or 1..parts) per row; rows with a missing value or weight get NA."""
    ok = value.notna() & weight.notna() & (weight > 0)
    q = quintile_matrix(value.where(ok), weight.where(ok, 0).to_numpy(), ids, parts)[:, 0]
    return pd.Series(q, index=value.index, dtype="Int64").where(ok.to_numpy(), pd.NA)


ELSTAT_TYPES = {"1": "A1", "2": "A2", "3": "A_GE3", "4": "A1_DCH", "5": "A2_DCH", "6": "A_GE3_DCH"}


def dependent_child(persons: pd.DataFrame) -> pd.Series:
    """True for a dependent child (see the module docstring), per person."""
    young = (persons.age >= 16) & (persons.age <= 24) & (persons.relation == "3") & ~persons.activity.isin(["1", "2"])
    return (persons.age < 16) | young


def household_type(survey: Survey) -> pd.Series:
    """Each household's type (aligned with survey.households); NA without person records or with
    no adult (not seen in the data)."""
    p = survey.persons
    dep = dependent_child(p)
    g = p.assign(adult=~dep, dep=dep).groupby("hh").agg(adults=("adult", "sum"), deps=("dep", "sum"))
    base = g.adults.clip(upper=3).map({1: "A1", 2: "A2", 3: "A_GE3"})
    t = (base + np.where(g.deps > 0, "_DCH", "")).where(g.adults > 0)
    return pd.Series(survey.households.hh.map(t).to_numpy(), dtype="string")


def tenure(survey: Survey) -> pd.Series:
    """renter / owner / rent_free, from the main-residence rent columns, in that order of priority;
    NA for a household with none of them (one or two a year).

    The older classification's "other imputed rentals" (0422) also holds imputed rent on
    second homes (04222); there the narrower "housed free" code (04221) is used instead.
    """
    s = survey.spending
    other = "04221" if "04221" in s.columns else "0422"
    for code in ("0411", "0421", other):
        if code not in s.columns:
            raise KeyError(f"{survey.year}: no spending column {code} for tenure")
    renter, owner, free = s["0411"] > 0, s["0421"] > 0, s[other] > 0
    out = np.select([renter, owner, free], ["renter", "owner", "rent_free"], default="")
    return pd.Series(out, index=s.index).replace("", pd.NA)


def total_spending(survey: Survey) -> pd.Series:
    """All-modes consumption spending: the sum of the finest codes, the same spending the shares
    describe. (The files' own division columns aren't always that sum: in 2008-2010 division 04
    is larger by an amount that isn't in any housing group nor in ELSTAT's published table.)"""
    from traceconomics.local.shares import leaves
    s = survey.spending
    return s[leaves(s.columns)].sum(axis=1)


def ranking(survey: Survey) -> tuple[pd.DataFrame, pd.Series]:
    """(the value each quintile grouping ranks by, one column per grouping; household size).

    A ranks households, so its weight is the household weight; B and C rank people, so
    theirs is the household weight times the household's size (`PEOPLE`)."""
    h = survey.households
    size = household_size(survey).reindex(h.hh).reset_index(drop=True)
    values = pd.DataFrame({
        "A": h.money_income,
        "B": h.money_income / size.scale,
        "C": total_spending(survey) / size.scale,
    })
    return values, size["size"]


PEOPLE = {"A": False, "B": True, "C": True}

# Every grouping made by ranking: (the value it ranks by, see `ranking`; whether it ranks people
# rather than households; how many equal parts; label prefix).
RANKED = {
    "A": ("A", False, 5, "Q"),
    "B": ("B", True, 5, "Q"),
    "C": ("C", True, 5, "Q"),
    # Only to check our method against studies with other settings, never published:
    # people in tenths of equivalised income, and households (not people) by equivalised income.
    "B10": ("B", True, 10, "D"),
    "BH": ("B", False, 5, "Q"),
    "BH10": ("B", False, 10, "D"),
}
VALIDATION_ONLY = ("B10", "BH", "BH10")


def assign(survey: Survey) -> pd.DataFrame:
    """One row per household (aligned with survey.households): its group in each grouping."""
    h = survey.households
    values, size = ranking(survey)
    people = h.weight * size
    ids = h.hh
    groups = pd.DataFrame({
        **{g: quintiles(values[v], people if by_people else h.weight, ids, parts)
           for g, (v, by_people, parts, _) in RANKED.items()},
        "tenure": tenure(survey),
        "pensioners": pd.Series(np.where(h.main_income_source == PENSION, "pensioners", "other"))
                        .where(h.main_income_source != "", pd.NA),
        "hhtype": household_type(survey),
        "all": "all",
    })
    for g, (_, _, _, prefix) in RANKED.items():
        groups[g] = prefix + groups[g].astype("string")   # NA stays NA
    groups["size"] = size
    groups["people_weight"] = people
    return groups
