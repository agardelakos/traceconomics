"""What the sensitivity checks share: a survey's group baskets, built the way the weights run
builds them, so a check can change the survey (put spending back, reweight households) and
rebuild the series on the result. The survey's weights are calibrated as the weights run
calibrates them, so a check measures its change on top of the published method.

Only the default basket is built: purchases, imputed rent excluded. The checks measure how far
the default series move (the headline figures always use the default setting); the other options
are not measured.
"""

from __future__ import annotations

import pandas as pd

from traceconomics.local.puf import Survey
from traceconomics.local.shares import shares
from traceconomics.module1.schedule import unusable
from traceconomics.module1.weights_used import Basket

SPENDING = "purchases"
IMPUTED_RENT_EXCLUDED = 1  # `shares`' option 1: imputed rent dropped and the rest rescaled


def baskets_from(year: int, mapped: Survey, groups: pd.DataFrame, wanted) -> dict[tuple[int, str, str], Basket]:
    """{(survey year, grouping, group): Basket} for the wanted (grouping, group) pairs.

    `mapped` is the survey in COICOP 2018 codes, `groups` its households' groups, both with the
    weights calibrated as the weights run calibrates them (`weights.prepare`). Groups the weights
    run leaves out (a survey whose incomes can't rank households) are left out here too."""
    t = shares(mapped, groups, SPENDING)
    t = t[t.imputed_rent == IMPUTED_RENT_EXCLUDED]
    out = {}
    for (grouping, label), part in t.groupby(["grouping", "group"]):
        if (grouping, label) in wanted and not unusable(grouping, year):
            out[(year, grouping, label)] = Basket(
                dict(zip(part.code, part.share)), dict(zip(part.code, part.reliability))
            )
    return out
