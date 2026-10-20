"""Every combination of module 1's user options, and the table saying which are available when.

The options (each with a default, the first value listed):

    spending        purchases | all          what a household's basket counts
    imputed_rent    excluded | included      owners' imputed rent, priced with actual rents if kept
    price_source    cpi | hicp               ELSTAT's national CPI or Eurostat's HICP item indices
    weights_timing  N | F | U                which survey's pattern each year uses (`schedule`)
    tutoring        priced | excluded        tutoring from 2026, when the CPI stops weighting it

and the grouping of the quintile groups (A, B, C). The all-households, tenure and pensioner
groups don't depend on the grouping, so every setting has 15 quintile groups and 6 others.

Every combination is computed on its own, even where two must come out the same (the two
tutoring options before 2026): the checks then confirm that they do, which catches an option
passed to the wrong place.
"""

from __future__ import annotations

import itertools

from traceconomics.module1 import index
from traceconomics.module1.index import DEFAULT_OPTIONS
from traceconomics.module1.prices import hicp_blocks
from traceconomics.module1.weights_used import load_baskets

OPTIONS = {
    "spending": ("purchases", "all"),
    "imputed_rent": ("excluded", "included"),
    "price_source": ("cpi", "hicp"),
    "weights_timing": ("N", "F", "U"),
    "tutoring": ("priced", "excluded"),
}
GROUPINGS = ("A", "B", "C")
QUINTILE_GROUPS = [(g, f"Q{k}") for g in GROUPINGS for k in range(1, 6)]
OTHER_GROUPS = [g for g in index.PUBLISHED_GROUPS if g[0] not in GROUPINGS]
GROUPS = QUINTILE_GROUPS + OTHER_GROUPS
DEFAULT = {"spending": "purchases", **DEFAULT_OPTIONS}


def settings() -> list[dict[str, str]]:
    """All 48 settings, the default first."""
    names = list(OPTIONS)
    out = [dict(zip(names, values)) for values in itertools.product(*OPTIONS.values())]
    out.sort(key=lambda s: s != DEFAULT)
    return out


def label(setting: dict) -> str:
    return "/".join(setting[k] for k in OPTIONS)


def iterate(con, archive, *, when=None, only=None, groups=None):
    """(setting, its series, {price source: blocks}) for every setting in `only` (default: all 48),
    one setting at a time, so a caller can write and drop each before the next."""
    blocks = {"cpi": index.price_blocks(con, archive, when), "hicp": hicp_blocks(con, when=when)}
    baskets = {}
    for setting in only or settings():
        key = (setting["spending"], setting["imputed_rent"])
        if key not in baskets:
            baskets[key] = load_baskets(con, spending=key[0], imputed_rent=key[1])
        options = {k: setting[k] for k in DEFAULT_OPTIONS}
        series = [index.build(con, grouping, group, spending=setting["spending"],
                              blocks=blocks[setting["price_source"]], baskets=baskets[key], first_year=None,
                              options=options)
                  for grouping, group in groups or GROUPS]
        yield setting, series, blocks
