"""The hospital-services check: how much the series change if the
hospital spending the 2008-2014 public use files leave out were put back.

Those files have no hospital services (06.3) at all, while ELSTAT's published table 1.03 gives
the average spent per household in each of its bands (income bands, or household size in 2013).
Each household gets its band's average, the groups' shares are recomputed, and the series are
rebuilt for the years those surveys feed; the report is the change in each group's annual-average
rate and in the Q1-Q5 gap. Bands are rebuilt as in V2: exactly where the counts match (2010-2013),
approximately otherwise (2008, 2009 and 2014: monthly money income rounded to the euro), and labelled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from traceconomics.archive.store import Archive
from traceconomics.local import mapping, puf, v2
from traceconomics.local.groups import assign
from traceconomics.local.shares import shares
from traceconomics.module1 import index
from traceconomics.module1.weights_used import Basket, load_baskets
from traceconomics.sources.elstat import hbs_tables

HOSPITAL_OLD = "06311"        # in the 2008-2014 tables
HOSPITAL_2018 = "06310"       # where the mapping sends the old group 06.3
SURVEYS = range(2008, 2015)   # the surveys behind index years 2009-2015 that lack it


def with_hospital(survey, table) -> tuple[pd.Series, str]:
    """Each household's yearly hospital spending, from its band's published monthly average."""
    by = v2.BANDED.get(survey.year, "income")
    band = v2.bands(survey, table, by)
    monthly = table.purchases.get(HOSPITAL_OLD, {})
    euros = band.map(lambda b: monthly.get(b, 0.0) or 0.0).astype(float) * 12
    how = f"{by} bands" + ("" if survey.year in v2.BANDED else ", approximate")
    return euros, how


def baskets_with_hospital(archive: Archive, year: int, groups_wanted) -> tuple[dict, str, float]:
    survey = puf.read(archive, year)
    groups = assign(survey)
    table = hbs_tables.parse(v2.archived_tables(archive)[year], year)
    euros, how = with_hospital(survey, table)
    mapped = mapping.to_2018(survey)
    p = mapped.purchases.copy()
    p[HOSPITAL_2018] = p.get(HOSPITAL_2018, 0.0) + euros.to_numpy()
    for parent in ("0631", "063", "06"):
        p[parent] = p.get(parent, 0.0) + euros.to_numpy()
    mapped.purchases = p
    t = shares(mapped, groups, "purchases")
    t = t[(t.imputed_rent == 1)]
    out = {}
    for (g, label), part in t.groupby(["grouping", "group"]):
        if (g, label) in groups_wanted:
            out[(year, g, label)] = Basket(dict(zip(part.code, part.share)), dict(zip(part.code, part.reliability)))
    w = survey.households.weight
    share = float((euros * w).sum() / (mapped.purchases[[c for c in mapped.purchases if len(c) == 2]].sum(axis=1) * w).sum())
    return out, how, share


def run(archive: Archive, con, groups_wanted=None) -> dict:
    groups_wanted = groups_wanted or index.PUBLISHED_GROUPS
    blocks = index.price_blocks(con, archive)
    base = load_baskets(con, spending="purchases")
    changed = dict(base)
    notes = {}
    for year in SURVEYS:
        extra, how, share = baskets_with_hospital(archive, year, set(groups_wanted))
        changed.update(extra)
        notes[year] = {"bands": how, "hospital_share_of_purchases": round(share, 4)}
    report = {"surveys": notes, "series": {}}
    rates = {}
    for g, label in groups_wanted:
        a = index.build(None, g, label, blocks=blocks, baskets=base)
        b = index.build(None, g, label, blocks=blocks, baskets=changed)
        ra, rb = a.annual_average_rates(), b.annual_average_rates()
        rates[(g, label)] = (ra, rb)
        report["series"][f"{g}/{label}"] = {y: round(rb[y] - ra[y], 3) for y in sorted(ra) if y <= 2016 and y in rb}
    if ("B", "Q1") in rates and ("B", "Q5") in rates:
        (a1, b1), (a5, b5) = rates[("B", "Q1")], rates[("B", "Q5")]
        report["gap_change"] = {y: round((b1[y] - b5[y]) - (a1[y] - a5[y]), 3) for y in sorted(a1) if y <= 2016}
    return report
