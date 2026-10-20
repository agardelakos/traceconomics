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

MAX_RATE_GAP = 0.1   # percentage points, on rates rounded to one decimal
MAX_LINK_GAP = 1e-3  # on the ratio to December of the previous year
_EPS = 1e-9


@dataclass
class Comparison:
    name: str
    months: int = 0                 # months with both rates
    exact: int = 0                  # of those, rounded rates equal
    worst_rate: tuple[str, float, float] | None = None   # period, ours, official
    worst_rate_gap: float = 0.0
    links: int = 0
    worst_link: tuple[str, float] | None = None          # period, gap
    failures: list[str] = field(default_factory=list)
    fallbacks: dict = field(default_factory=dict)
    min_covered: float = 1.0
    first: str | None = None
    last: str | None = None

    @property
    def passed(self) -> bool:
        return not self.failures and self.months > 0

    def summary(self) -> str:
        if not self.months:
            return f"{self.name}: no months to compare"
        lines = [
            f"{self.name}: {self.first} to {self.last}, {'PASS' if self.passed else 'FAIL'}",
            f"  annual rates: {self.months} months, {self.exact} exact "
            f"({self.exact / self.months:.0%}), largest gap {self.worst_rate_gap:.1f} pp"
            + (f" ({self.worst_rate[0]}: ours {self.worst_rate[1]:.1f}, official {self.worst_rate[2]:.1f})"
               if self.worst_rate and self.worst_rate_gap else ""),
            f"  links to December: {self.links} months, largest gap "
            + (f"{self.worst_link[1]:.1e} ({self.worst_link[0]})" if self.worst_link else "0"),
            f"  weight priced: at least {self.min_covered:.1%} in every month",
        ]
        if self.fallbacks:
            top = sorted(self.fallbacks.items(), key=lambda kv: -kv[1])[:8]
            lines.append("  priced with a parent's index (item -> parent: months): "
                         + "; ".join(f"{c} -> {u or 'none'}: {n}" for (c, u), n in top)
                         + (f"; and {len(self.fallbacks) - 8} more" if len(self.fallbacks) > 8 else ""))
        lines += [f"  FAIL {f}" for f in self.failures[:10]]
        if len(self.failures) > 10:
            lines.append(f"  ... and {len(self.failures) - 10} more failures")
        return "\n".join(lines)


def compare(name: str, result: ChainResult, official: dict[str, float],
            official_rates: dict[str, float] | None = None) -> Comparison:
    """`official`: the official all-items index by month. `official_rates`: published annual
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
        ours, theirs = round(ours, 1), round(theirs, 1)
        rate_gap = abs(ours - theirs)
        c.months += 1
        c.exact += rate_gap < _EPS
        if rate_gap > c.worst_rate_gap + _EPS:
            c.worst_rate_gap, c.worst_rate = rate_gap, (period, ours, theirs)
        if rate_gap > MAX_RATE_GAP + _EPS:
            c.failures.append(f"{period}: annual rate {ours:.1f} vs official {theirs:.1f}")
    return c
