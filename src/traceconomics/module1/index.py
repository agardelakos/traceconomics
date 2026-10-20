"""Module 1: each group's inflation, from the weights it uses and the CPI's item indices.

For every group: the weights-timing rule picks a survey for each index year; the weights used
are that survey's shares, priced and price-updated (`weights_used`); the engine chains the years
at December, each year with its own block of CPI prices. The index is rebased so that the 2025
average is 100, and published with two decimals; rates are computed from the published index and
shown with one decimal, as Eurostat does (HICP Methodological Manual 2024, section 11.4.6).

Every item must be priced in every month: a group whose coverage falls below 1 fails the run,
rather than quietly rescaling.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from traceconomics.checks import require
from traceconomics.engine import ChainResult, chain, rebase
from traceconomics.engine.rates import annual_average_rate, annual_rate, monthly_rate
from traceconomics.module1.prices import cpi_blocks  # noqa: F401  (re-exported for callers)
from traceconomics.module1.schedule import RULES, Entry
from traceconomics.module1.weights_used import CODED_2018_FROM, PRICED, Used, load_baskets, tutoring_fraction, weights_used

FIRST_YEAR = 2009          # linked at December 2008; 2009-2010 come from ELSTAT's original tables (`originals`)
LESS_CERTAIN_UNTIL = "2010-12"   # index months built on the original tables (an older version of the prices)
BASE_YEAR = 2025
# The user options (besides grouping and spending) and their defaults; every series carries its own.
DEFAULT_OPTIONS = {"imputed_rent": "excluded", "price_source": "cpi", "weights_timing": "N", "tutoring": PRICED}
PUBLISHED_GROUPS = (
    [("all", "all")]
    + [("B", f"Q{k}") for k in range(1, 6)]
    + [("tenure", g) for g in ("renter", "owner", "rent_free")]
    + [("pensioners", g) for g in ("pensioners", "other")]
)
# Only to compare with KEPE (its top tenth, and households ranked instead of people).
VALIDATION_GROUPS = [("B10", "D10")] + [("BH", f"Q{k}") for k in (1, 5)] + [("BH10", "D10")]


@dataclass
class Series:
    grouping: str
    group: str
    spending: str
    schedule: list[Entry]
    used: dict[int, Used]
    chained: ChainResult
    index: dict[str, float] = field(default_factory=dict)        # rebased, unrounded
    published: dict[str, float] = field(default_factory=dict)    # rebased, two decimals
    options: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_OPTIONS))
    base_year: int = BASE_YEAR
    tutoring_split: float | None = None    # the group's share of tutoring in 10.1 + 10.2 + 10.5, survey 2024

    @property
    def index_unit(self) -> str:
        """I25 for 2025 = 100; a series ending before 2025 is on its last complete year."""
        return f"I{self.base_year % 100:02d}"

    def rates(self) -> dict[str, dict[str, float]]:
        """period -> {"annual": ..., "monthly": ...}, from the published index (one decimal shown later)."""
        out = {}
        for period in sorted(self.published):
            a, m = annual_rate(self.published, period), monthly_rate(self.published, period)
            out[period] = {k: v for k, v in (("annual", a), ("monthly", m)) if v is not None}
        return out

    def annual_average_rates(self) -> dict[int, float]:
        years = sorted({int(p[:4]) for p in self.published})
        return {y: r for y in years if (r := annual_average_rate(self.published, y)) is not None}


def build(con, grouping: str, group: str, *, spending: str = "purchases", when=None,
          blocks=None, baskets=None, rule=None, first_year: int | None = FIRST_YEAR,
          options: dict | None = None) -> Series:
    """One group's series. `options` label it and choose its weights-timing rule and tutoring
    treatment (`blocks` and `baskets` must match its price source and imputed-rent option);
    `rule` overrides the timing rule, to rebuild other studies. `first_year` None: the first year
    the rule has weights for (from FIRST_YEAR on); a rule with no weights for a given
    `first_year` fails."""
    options = {**DEFAULT_OPTIONS, **(options or {})}
    rule = rule or RULES[options["weights_timing"]]
    blocks = cpi_blocks(con, when) if blocks is None else blocks
    baskets = load_baskets(con, spending=spending) if baskets is None else baskets
    surveys = {year for (year, g, label) in baskets if (g, label) == (grouping, group)}
    last = max(blocks)
    schedule = rule(range(first_year or FIRST_YEAR, last + 1), surveys)
    require(bool(schedule), f"{grouping}/{group}: no weights in any year")
    first_year = first_year or schedule[0].year
    require(schedule[0].year == first_year, f"{grouping}/{group}: no weights for {first_year}")
    split_basket = baskets.get((CODED_2018_FROM, grouping, group))
    split = tutoring_fraction(split_basket) if split_basket is not None else None
    used = {e.year: weights_used(baskets[(e.survey, grouping, group)], e, blocks, tutoring=options["tutoring"],
                                 tutoring_split=split) for e in schedule}
    result = chain({y: u.weights for y, u in used.items()}, blocks, first_year=first_year,
                   last_year=schedule[-1].year, base_value=100.0, by_year=True,
                   price_with={y: u.price_with for y, u in used.items()})
    short = {p: c for p, c in result.covered.items() if c < 1 - 1e-12}
    require(not short, f"{grouping}/{group} ({spending}): items left unpriced in {sorted(short)[:3]}")
    # 2025 = 100, or, for a series that ends earlier (same-year weights stop at the newest
    # survey), its last complete year; the rates don't depend on the choice.
    complete = [y for y in {int(p[:4]) for p in result.index}
                if all(f"{y}-{m:02d}" in result.index for m in range(1, 13))]
    base = BASE_YEAR if BASE_YEAR in complete else max(complete)
    index = rebase(result.index, base)
    published = {p: round(v, 2) for p, v in index.items()}
    return Series(grouping, group, spending, schedule, used, result, index, published, options, base, split)


def price_blocks(con, archive, when=None) -> dict:
    """The default prices: ELSTAT's re-issued table 07 from 2011, its original tables for 2008-2010."""
    from traceconomics.module1 import originals

    blocks = cpi_blocks(con, when)
    early, _ = originals.blocks(archive)
    blocks.update(early)
    return blocks


def build_all(con, archive, *, spending: str = "purchases", groups=None, when=None) -> list[Series]:
    blocks = price_blocks(con, archive, when)
    baskets = load_baskets(con, spending=spending)
    return [build(con, g, label, spending=spending, when=when, blocks=blocks, baskets=baskets)
            for g, label in (groups or PUBLISHED_GROUPS)]
