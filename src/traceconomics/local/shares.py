"""Spending shares per group and item: each group's basket.

A group's share of item i is the group's total spending on i divided by its
total spending on everything in scope (plutocratic weights: a household counts
in proportion to what it spends; CPI Manual 2020 ¶1.35, ¶3.18).

Which spending (`SPENDING`, the user chooses):
- "purchases": monetary spending only, the concept of the CPI's and the HICP's own
  weights ("household final monetary consumption expenditure");
- "all": all modes, adding own production and income in kind (goods and services
  received from an employer or another household), which weigh more in poorer
  households' budgets.

- Shares are computed on the finest codes (the leaves) and summed up the tree,
  so every level adds up exactly. Items the PUF leaves out simply aren't there:
  the rest is rescaled.
- Imputed rent (COICOP 04.2) is dropped and the rest rescaled under option 1,
  kept under option 2 (in either spending concept; it is never a purchase); the
  user chooses.
- Each share comes with the number of households in the group that reported any
  spending on it (unweighted), and the Eurostat publication tier that count
  implies: under 20 "suppressed" (never shown alone; priced at the parent level),
  20-49 "flagged", 50 or more "normal" (Eurostat's publication thresholds for
  household surveys).

The sums are matrix products over households, so the same code serves one set of
weights (the estimate) or many (bootstrap replicates, see `bootstrap`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from traceconomics.local.groups import VALIDATION_ONLY, assign
from traceconomics.local.puf import Survey

IMPUTED_RENT = "042"
SPENDING = ("purchases", "all")
GROUPINGS = ("all", "A", "B", "C", "tenure", "pensioners", *VALIDATION_ONLY)
PUBLISHED = tuple(g for g in GROUPINGS if g not in VALIDATION_ONLY)


def leaves(codes) -> list[str]:
    codes = [c for c in codes if c != "00"]
    return sorted(c for c in codes if not any(o != c and o.startswith(c) for o in codes))


def reliability(n: int) -> str:
    return "suppressed" if n < 20 else "flagged" if n < 50 else "normal"


@dataclass
class Tree:
    """The leaves in scope under one imputed-rent option, and every code above them."""
    option: int
    leaves: list[str]
    codes: list[str]
    incidence: np.ndarray      # codes x leaves: 1 where the leaf sits under (or is) the code

    @classmethod
    def build(cls, all_leaves: list[str], option: int) -> Tree:
        kept = [c for c in all_leaves if option == 2 or not c.startswith(IMPUTED_RENT)]
        parents = {c[:k] for c in kept for k in range(2, len(c))}
        codes = sorted(set(kept) | parents)
        incidence = np.array([[leaf.startswith(code) for leaf in kept] for code in codes], dtype=float)
        return cls(option, kept, codes, incidence)


def group_shares(x: np.ndarray, weights: np.ndarray, tree: Tree) -> np.ndarray:
    """codes x R shares, from x (households x leaves, euros) and weights (households x R) that are
    already zero outside the group."""
    sums = x.T @ weights                         # leaves x R
    return tree.incidence @ sums / sums.sum(axis=0)


def basket(survey: Survey, spending: str, option: int) -> tuple[Tree, np.ndarray]:
    """The leaves in scope and households x leaves euros, for one spending concept and
    imputed-rent option."""
    if spending == "all":
        frame = survey.spending
        tree = Tree.build(leaves(frame.columns), option)
    elif spending == "purchases":
        frame = survey.purchases
        kept = [c for c in leaves(frame.columns) if not c.startswith(IMPUTED_RENT)]
        if option == 2:
            # Imputed rent is never paid for; option 2 adds it, as valued in the survey.
            rent = [c for c in leaves(survey.spending.columns) if c.startswith(IMPUTED_RENT)]
            frame = pd.concat([frame[kept], survey.spending[rent]], axis=1)
            kept = kept + rent
        tree = Tree.build(sorted(kept), option)
    else:
        raise ValueError(spending)
    return tree, frame[tree.leaves].to_numpy(float)


def memberships(groups: pd.DataFrame, groupings=GROUPINGS) -> list[tuple[str, str, np.ndarray]]:
    """(grouping, group, member mask) for every group; households without a group are in none."""
    out = []
    for grouping in groupings:
        labels = groups[grouping]
        for group in sorted(labels.dropna().unique()):
            out.append((grouping, group, (labels == group).fillna(False).to_numpy(bool)))
    return out


def shares(survey: Survey, groups: pd.DataFrame | None = None, spending: str = "purchases") -> pd.DataFrame:
    """Long table: grouping, group, imputed_rent, code, digits, leaf, share, n_reporting, reliability,
    plus the group's sample size and weighted households."""
    groups = assign(survey) if groups is None else groups
    w = survey.households.weight.to_numpy(float)
    rows = []
    for option in (1, 2):
        tree, x = basket(survey, spending, option)
        reporting = (x > 0).astype(float)
        for grouping, group, member in memberships(groups):
            share = group_shares(x, (w * member)[:, None], tree)[:, 0]
            # Households that reported anything under each code (at a leaf: on the item itself).
            n = ((reporting[member] @ tree.incidence.T) > 0).sum(axis=0)
            for code, s, k in zip(tree.codes, share, n):
                rows.append({
                    "grouping": grouping, "group": group, "imputed_rent": option,
                    "code": code, "digits": len(code), "leaf": code in tree.leaves,
                    "share": float(s), "n_reporting": int(k), "reliability": reliability(int(k)),
                    "n_households": int(member.sum()),
                    "households_weighted": float(w[member].sum()),
                })
    return pd.DataFrame(rows)
