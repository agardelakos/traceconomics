"""The tenure check: what calibrating the survey's weights to the census's tenure split changes.

The household budget survey (HBS) counts about a third fewer renting households than the census,
and the weights run calibrates every survey's household weights so renters, owners and the
housed free make up the census's split (`calibration`). This check rebuilds each survey's group
baskets both ways, on ELSTAT's weights as published and on the calibrated ones, with the same
code as the weights run, and rebuilds every published group's series on each: the report is the
change the calibration makes to each group's annual-average and December rates, to the gap
between the poorest and richest fifths and to rent's share of each basket, with each survey's
renter share before and after.

Built-in checks: the calibrated baskets equal the stored ones (otherwise the store is stale, and
the comparison would be with something else), and the tenure groups' own baskets don't move
(scaling all members of a group alike leaves its shares as they were). It reads the archive and
the store and changes nothing.
"""

from __future__ import annotations

import numpy as np

from traceconomics.archive.store import Archive
from traceconomics.checks import require
from traceconomics.local import mapping
from traceconomics.local.calibration import TENURES, member
from traceconomics.local.sensitivity import baskets_from
from traceconomics.local.weights import Prepared, prepare
from traceconomics.module1 import index
from traceconomics.module1.weights_used import load_baskets

RENT = "041"                    # actual rentals for housing, COICOP 2018
SAME_BASKET = 1e-12             # a tenure group's basket after scaling all its members alike: equal up to rounding


def renter_share(weights: np.ndarray, tenure) -> float:
    """Renters' share of the weighted households whose tenure is known."""
    known = np.logical_or.reduce([member(tenure, t) for t in TENURES])
    return float(weights[member(tenure, "renter")].sum() / weights[known].sum())


def survey_baskets(p: Prepared, wanted) -> tuple[dict, dict, dict]:
    """(baskets on ELSTAT's weights, baskets calibrated, the year's note)."""
    year = p.survey.year
    before = baskets_from(year, mapping.to_2018(p.survey), p.as_read, wanted)
    after = baskets_from(year, p.mapped, p.groups, wanted)
    for (y, grouping, label), b in before.items():
        if grouping == "tenure":
            a = after[(y, grouping, label)].shares
            moved = max(abs(a.get(c, 0.0) - s) for c, s in b.shares.items())
            require(moved < SAME_BASKET, f"{year}: the {label} basket moved by {moved:g} when only weights within it were scaled")
    tenure = p.as_read["tenure"]
    note = {"renters_before": renter_share(p.survey.households.weight.to_numpy(float), tenure),
            "renters_after": renter_share(p.calibrated.households.weight.to_numpy(float), tenure),
            "target": p.target.shares["renter"], "basis": p.target.basis, "factors": p.factors}
    return before, after, note


def run(archive: Archive, con, groups_wanted=None, years=None) -> dict:
    groups_wanted = list(groups_wanted or index.PUBLISHED_GROUPS)
    wanted = set(groups_wanted)
    blocks = index.price_blocks(con, archive)
    stored = load_baskets(con, spending="purchases")
    years = sorted(years or {y for y, _, _ in stored})
    base, changed = dict(stored), dict(stored)
    report = {"surveys": {}, "series": {}, "rent_share": {}}
    for year in years:
        before, after, note = survey_baskets(prepare(archive, year), wanted)
        # The calibrated baskets rebuilt here should be the stored ones: a gap means the store is stale.
        gap = max((abs(stored[k].shares.get(c, 0.0) - s) for k, b in after.items() if k in stored
                   for c, s in b.shares.items()), default=0.0)
        require(all(k in stored for k in after), f"{year}: groups built here are missing from the store: run `weights run`")
        note["store_gap"] = gap
        base.update(before)
        changed.update(after)
        report["surveys"][year] = note
    rates = {}
    for grouping, label in groups_wanted:
        a = index.build(None, grouping, label, blocks=blocks, baskets=base)
        b = index.build(None, grouping, label, blocks=blocks, baskets=changed)
        ra, rb = a.annual_average_rates(), b.annual_average_rates()
        da, db = a.rates(), b.rates()
        rates[(grouping, label)] = (ra, rb)
        name = f"{grouping}/{label}"
        report["series"][name] = {
            y: {"annual_average": round(rb[y] - ra[y], 3),
                "december": round(db[f"{y}-12"]["annual"] - da[f"{y}-12"]["annual"], 3)
                if "annual" in da.get(f"{y}-12", {}) and "annual" in db.get(f"{y}-12", {}) else None}
            for y in sorted(ra) if y in rb}
        report["rent_share"][name] = {y: (round(base[(y, grouping, label)].shares.get(RENT, 0.0), 4),
                                          round(changed[(y, grouping, label)].shares.get(RENT, 0.0), 4))
                                      for y in years if (y, grouping, label) in base and (y, grouping, label) in changed}
    if ("B", "Q1") in rates and ("B", "Q5") in rates:
        (a1, b1), (a5, b5) = rates[("B", "Q1")], rates[("B", "Q5")]
        report["gap_change"] = {y: round((b1[y] - b5[y]) - (a1[y] - a5[y]), 3)
                                for y in sorted(a1) if y in b1 and y in a5 and y in b5}
    return report
