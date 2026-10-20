"""The weights each index year actually uses: survey shares, priced and price-updated.

For an index year y and a group, from the survey chosen by the weights-timing rule:

1. take the group's shares on the finest codes (the leaves);
2. decide which index prices each leaf (`pricing_map`), in this order:
   - an item with no index under the method is dropped and the rest rescaled: games of chance
     (09.4.7) while the price source has no index for them;
   - education not defined by level (10.5, mostly tutoring) is priced with secondary education
     (10.2), where tutoring prices are collected, whenever the price source has no 10.5 index
     for the year (the CPI never has one; the HICP has one until 2014);
   - imputed rent (04.2, kept only under the option that keeps it) has no price index in the CPI
     or the HICP, and is priced with actual rents paid by tenants (04.1.1), the rental-equivalence
     approach;
   - a leaf reported by fewer than 20 sampled households in the group is priced at the level of
     its nearest ancestor reported by 20 or more (Eurostat's "not published" tier; pricing
     unreliable cells at a sturdier level);
   - otherwise its own index, and failing that its nearest ancestor's (the engine's search);
3. price-update each share from the survey year's average prices to December y-1, with the
   index that prices it, and rescale to 1:  w = s * P(Dec y-1) / P(average of survey year).

Under the option that leaves tutoring out from 2026 (as ELSTAT's CPI does from that year, by
giving 10.5 no weight), 10.5 is removed before step 3. A survey coded in COICOP 2018 (from 2024)
holds tutoring in 10.5 alone. An older survey filed it under the school level it served, inside
10.1 and 10.2, where it can't be told apart; there the group's own split in the first survey
coded both ways is used (`tutoring_fraction`): that share of the group's 10.1 + 10.2 + 10.5 is
removed, first all of 10.5, then the rest from 10.1 and 10.2 in proportion.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

from traceconomics.checks import require
from traceconomics.engine.chain import DROP, Prices
from traceconomics.engine.tree import ancestors
from traceconomics.module1.prices import update_factor
from traceconomics.module1.schedule import Entry

GAMES_OF_CHANCE = "0947"
NOT_BY_LEVEL, SECONDARY = "105", "1020"
BY_LEVEL = ("101", "102")
IMPUTED_RENT, ACTUAL_RENTS = "042", "0411"
PRICED, EXCLUDED = "priced", "excluded"
TUTORING_EXCLUDED_FROM = 2026      # the first year ELSTAT's CPI gives 10.5 no weight
CODED_2018_FROM = 2024             # the first survey coded in COICOP 2018, with tutoring in 10.5
SUPPRESSED = "suppressed"


@dataclass(frozen=True)
class Basket:
    """One group's survey basket: code -> share (every level) and code -> reliability tier."""
    shares: dict[str, float]
    reliability: dict[str, str]

    def leaves(self) -> dict[str, float]:
        codes = [c for c, s in self.shares.items() if s > 0]
        return {c: self.shares[c] for c in codes if not any(o != c and o.startswith(c) for o in codes)}


def has_index(block: Prices, code: str) -> bool:
    """Whether the block holds an index for the code or anything below it."""
    return any(c.startswith(code) for c in block)


def pricing_map(basket: Basket, block: Prices) -> dict[str, str]:
    """leaf -> the code whose index prices it, or DROP (see the module docstring)."""
    out = {}
    for leaf in basket.leaves():
        if leaf.startswith(GAMES_OF_CHANCE) and not has_index(block, GAMES_OF_CHANCE):
            out[leaf] = DROP
        elif leaf.startswith(NOT_BY_LEVEL) and not has_index(block, NOT_BY_LEVEL):
            out[leaf] = SECONDARY
        elif leaf.startswith(IMPUTED_RENT):
            out[leaf] = ACTUAL_RENTS
        elif basket.reliability.get(leaf) == SUPPRESSED:
            sturdier = next((a for a in ancestors(leaf) if basket.reliability.get(a) != SUPPRESSED), None)
            if sturdier is not None:
                out[leaf] = sturdier
    return out


@dataclass
class Used:
    entry: Entry
    weights: dict[str, float]                  # leaf -> price-updated weight (sums to 1; dropped leaves absent)
    price_with: dict[str, str]
    dropped: dict[str, float] = field(default_factory=dict)   # leaf -> survey share removed (all or part)
    update_paths: dict[str, list[str]] = field(default_factory=dict)
    # leaf -> the nearest ancestor whose cell has 20+ reporting households, for leaves whose own
    # cell has fewer: published only inside a "rest of" that ancestor, never alone.
    small: dict[str, str] = field(default_factory=dict)


def tutoring_fraction(basket: Basket) -> float:
    """10.5's share of 10.1 + 10.2 + 10.5 in a survey coded in COICOP 2018."""
    s = basket.shares
    level = sum(s.get(c, 0.0) for c in BY_LEVEL)
    not_by_level = s.get(NOT_BY_LEVEL, 0.0)
    total = level + not_by_level
    return not_by_level / total if total > 0 else 0.0


def exclude_tutoring(leaves: dict[str, float], fraction: float | None) -> tuple[dict[str, float], dict[str, float]]:
    """(leaves without tutoring, {leaf: share removed}); see the module docstring.
    `fraction` None: the survey is coded in COICOP 2018, so all of 10.5 goes and nothing else."""
    not_by_level = {c: v for c, v in leaves.items() if c.startswith(NOT_BY_LEVEL)}
    level = {c: v for c, v in leaves.items() if c.startswith(BY_LEVEL)}
    removed = dict(not_by_level)
    rest = 0.0
    if fraction is not None:
        rest = max(fraction * (sum(level.values()) + sum(not_by_level.values())) - sum(not_by_level.values()), 0.0)
    out = {c: v for c, v in leaves.items() if c not in not_by_level}
    if rest > 0:
        keep = 1 - rest / sum(level.values())
        for c, v in level.items():
            out[c] = v * keep
            removed[c] = v - out[c]
    return out, removed


def weights_used(basket: Basket, entry: Entry, blocks: dict[int, Prices], *, tutoring: str = PRICED,
                 tutoring_split: float | None = None) -> Used:
    """`tutoring_split`: the group's `tutoring_fraction` in the first survey coded in COICOP 2018,
    needed only to leave tutoring out with an older survey."""
    require(tutoring in (PRICED, EXCLUDED), f"unknown tutoring option {tutoring}")
    leaves = basket.leaves()
    pmap = pricing_map(basket, blocks.get(entry.year, {}))
    raw, paths, dropped = {}, {}, {}
    if tutoring == EXCLUDED and entry.year >= TUTORING_EXCLUDED_FROM:
        old = entry.survey < CODED_2018_FROM
        require(not old or tutoring_split is not None,
                f"{entry.year}: survey {entry.survey} needs the group's tutoring split to leave tutoring out")
        leaves, dropped = exclude_tutoring(leaves, tutoring_split if old else None)
    for leaf, share in leaves.items():
        start = pmap.get(leaf, leaf)
        if start == DROP:
            dropped[leaf] = share
            continue
        if entry.survey >= entry.year:
            # A survey of the index year itself (only to rebuild studies that do this) has no
            # earlier prices to update from: its shares are used as they are.
            raw[leaf], paths[leaf] = share, []
            continue
        f = update_factor(blocks, start, entry.survey, entry.year)
        require(f is not None, f"{entry.year}: no index to price-update {leaf} (from {start}) since {entry.survey}")
        raw[leaf] = share * f[0]
        paths[leaf] = f[1]
    total = sum(raw.values())
    small = {leaf: next((a for a in ancestors(leaf) if basket.reliability.get(a) != SUPPRESSED), "")
             for leaf in raw if basket.reliability.get(leaf) == SUPPRESSED}
    return Used(entry, {c: v / total for c, v in raw.items()}, pmap, dropped, paths, small)


def load_baskets(con: duckdb.DuckDBPyConnection, *, spending: str, imputed_rent: str = "excluded",
                 geo: str = "GR") -> dict[tuple[int, str, str], Basket]:
    """{(survey year, grouping, group): Basket} from the store's weights tables."""
    rows = con.execute("""
        SELECT ref_period, grouping, "group", coicop18, measure, value, value_text FROM observations
        WHERE dataset = 'oet-local:hbs_weights' AND geo = $geo AND spending = $sp AND imputed_rent = $ir
          AND measure IN ('share', 'reliability')
        QUALIFY row_number() OVER (PARTITION BY key, ref_period ORDER BY published_at DESC, retrieved_at DESC) = 1
            AND status <> 'withdrawn'
    """, {"geo": geo, "sp": spending, "ir": imputed_rent}).fetchall()
    shares: dict[tuple, dict] = {}
    tiers: dict[tuple, dict] = {}
    for year, grouping, group, code, measure, value, text in rows:
        k = (int(year), grouping, group)
        if measure == "share":
            shares.setdefault(k, {})[code] = value
        else:
            tiers.setdefault(k, {})[code] = text
    return {k: Basket(s, tiers.get(k, {})) for k, s in shares.items()}
