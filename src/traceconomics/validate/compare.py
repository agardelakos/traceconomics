"""Compare a rebuilt index with the official one.

The pass rule is the strictest one that rebuilding can meet. Official
annual rates are computed from the published all-items index, which is
rounded to two decimals. A rebuilt index comes from sub-indices and weights
that are themselves rounded, so it can land on the other side of a rounding
boundary: on Greek HICP data about one month in twenty is 0.1 percentage
points off, and none further. So a month passes when the rounded rates
differ by at most 0.1, and the link to December (the part the engine
computes) is within 0.001 of the official link.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from traceconomics.engine import ChainResult
from traceconomics.engine.chain import link_month
from traceconomics.engine.rates import annual_rate

MAX_RATE_GAP = 0.1  # percentage points, on rates rounded to one decimal
MAX_LINK_GAP = 1e-3  # on the ratio to December of the previous year
_EPS = 1e-9


@dataclass
class Comparison:
    """A rebuilt index against the official one: rate and link gaps, coverage, fallbacks and failures."""

    name: str
    months: int = 0  # months with both rates
    exact: int = 0  # of those, rounded rates equal
    worst_rate: tuple[str, float, float] | None = None  # period, ours, official
    worst_rate_gap: float = 0.0
    links: int = 0
    worst_link: tuple[str, float] | None = None  # period, gap
    failures: list[str] = field(default_factory=list)
    fallbacks: dict = field(default_factory=dict)
    min_covered: float = 1.0
    first: str | None = None
    last: str | None = None
    # Every month with both rates: (period, ours, official), before rounding. Kept so the
    # comparison can be published month by month, not only as these totals.
    rows: list[tuple[str, float, float]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when there were months to compare and nothing failed."""
        return not self.failures and self.months > 0

    def summary(self) -> str:
        """The comparison as a few lines of text for a report."""
        if not self.months:
            return f"{self.name}: no months to compare"
        lines = [
            f"{self.name}: {self.first} to {self.last}, {'PASS' if self.passed else 'FAIL'}",
            f"  annual rates: {self.months} months, {self.exact} exact "
            f"({self.exact / self.months:.0%}), largest gap {self.worst_rate_gap:.1f} pp"
            + (
                f" ({self.worst_rate[0]}: ours {self.worst_rate[1]:.1f}, official {self.worst_rate[2]:.1f})"
                if self.worst_rate and self.worst_rate_gap
                else ""
            ),
            f"  links to December: {self.links} months, largest gap "
            + (f"{self.worst_link[1]:.1e} ({self.worst_link[0]})" if self.worst_link else "0"),
            f"  weight priced: at least {self.min_covered:.1%} in every month",
        ]
        if self.fallbacks:
            top = sorted(self.fallbacks.items(), key=lambda kv: -kv[1])[:8]
            lines.append(
                "  priced with a parent's index (item -> parent: months): "
                + "; ".join(f"{c} -> {u or 'none'}: {n}" for (c, u), n in top)
                + (f"; and {len(self.fallbacks) - 8} more" if len(self.fallbacks) > 8 else "")
            )
        lines += [f"  FAIL {f}" for f in self.failures[:10]]
        if len(self.failures) > 10:
            lines.append(f"  ... and {len(self.failures) - 10} more failures")
        return "\n".join(lines)


def compare(
    name: str, result: ChainResult, official: dict[str, float], official_rates: dict[str, float] | None = None
) -> Comparison:
    """A rebuilt index's links and annual rates against the official ones, month by month.

    `official`: the official all-items index by month. `official_rates`: published annual
    rates (one decimal); if missing, they're computed from `official`, as the publishers do."""
    c = Comparison(name=name, fallbacks=result.fallback_summary())
    periods = sorted(result.links)
    if periods:
        c.first, c.last = periods[0], periods[-1]
    for period in periods:
        base = link_month(int(period[:4]))
        if period not in official or base not in official:
            continue
        gap = abs(result.links[period] - official[period] / official[base])
        c.links += 1
        if c.worst_link is None or gap > c.worst_link[1]:
            c.worst_link = (period, gap)
        if gap > MAX_LINK_GAP:
            c.failures.append(f"{period}: link differs by {gap:.1e}")
        c.min_covered = min(c.min_covered, result.covered.get(period, 1.0))

        ours = annual_rate(result.index, period)
        theirs = official_rates.get(period) if official_rates is not None else annual_rate(official, period)
        if ours is None or theirs is None:
            continue
        c.rows.append((period, ours, theirs))
        ours, theirs = round(ours, 1), round(theirs, 1)
        rate_gap = abs(ours - theirs)
        c.months += 1
        c.exact += rate_gap < _EPS
        if rate_gap > c.worst_rate_gap + _EPS:
            c.worst_rate_gap, c.worst_rate = rate_gap, (period, ours, theirs)
        if rate_gap > MAX_RATE_GAP + _EPS:
            c.failures.append(f"{period}: annual rate {ours:.1f} vs official {theirs:.1f}")
    return c


def repeated_baskets(weights: dict[int, dict[str, float]], first: int, last: int) -> list[str]:
    """A failure for each year from `first` to `last` whose weights equal the year before's.

    Both publishers reweight every year: ELSTAT's CPI from 2014 (2012 and 2013 kept 2011's fixed
    basket) and Eurostat's HICP for Greece in every year from 1996 to 2026 (checked on the archive,
    2026-11-22). A year that repeats the year before's basket means the new one wasn't read. The
    index can't show it in January, the one month when it matters most: replayed on every January
    from 2015 to 2026, a correct January missed the official link to December by up to 1.1e-4 and
    last year's basket by as little as 1.0e-4, so no tolerance on the link separates the two.
    """
    return [
        f"{y}: the weights are the same as {y - 1}'s (the new year's basket wasn't read)"
        for y in range(first, last + 1)
        if y in weights and y - 1 in weights and weights[y] == weights[y - 1]
    ]


def behind(last_checked: str | None, newest: str | None) -> str | None:
    """A failure if the check stopped before the newest month the store holds; None otherwise.

    A check that passes on everything but the newest month says nothing about the month a release
    is about to publish (a January file it didn't recognise, say), so it must not pass.
    """
    if newest is None or (last_checked is not None and last_checked >= newest):
        return None
    return f"checked to {last_checked or 'no month'}, but the store holds {newest}: the newest months weren't checked"
