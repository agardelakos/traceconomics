"""Annual chain-linking at December.

For each year y, with weights w_i fixed for the whole year and the price
index P_i of each item:

    link(y, m)  = sum_i w_i * P_i(y, m) / P_i(Dec y-1)  /  sum_i w_i
    I(y, m)     = I(Dec y-1) * link(y, m)

so December of the previous year is the link month: each year is computed
relative to it, and the years are multiplied together. This is how the HICP
(HICP Methodological Manual 2024, section 2.4) and the Greek CPI are built.

Prices can be on any base (2015=100, 2020=100, ...): only ratios within an
item's own series are used.

Two options keep the method out of the engine but let it say what to do:
- `prices` may be given per year, so each year is linked with its own copy of
  the previous December (a source that publishes one file a year can print the
  same December twice, with different digits);
- `price_with` maps, per year, a weighted item to the code whose index prices
  it (the search for an index then starts there and climbs its ancestors), or
  to DROP, which takes the item out of that year's basket and rescales the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from traceconomics.engine.tree import ancestors, leaves

Prices = dict[str, dict[str, float]]   # code -> {"YYYY-MM": index}
Weights = dict[int, dict[str, float]]  # year -> {code: weight}, any unit
PriceWith = dict[str, str]             # weighted code -> code that prices it, or DROP
DROP = "drop"


@dataclass(frozen=True)
class Fallback:
    period: str
    code: str
    used: str | None   # the ancestor whose index priced it; None if nothing could


@dataclass
class ChainResult:
    index: dict[str, float] = field(default_factory=dict)   # period -> chained index
    links: dict[str, float] = field(default_factory=dict)   # period -> link to December of the previous year
    covered: dict[str, float] = field(default_factory=dict) # period -> share of leaf weight that was priced
    fallbacks: list[Fallback] = field(default_factory=list)

    def fallback_summary(self) -> dict[tuple[str, str | None], int]:
        """(code, ancestor used) -> number of months, for reports."""
        out: dict[tuple[str, str | None], int] = {}
        for f in self.fallbacks:
            out[(f.code, f.used)] = out.get((f.code, f.used), 0) + 1
        return out


def link_month(year: int) -> str:
    return f"{year - 1}-12"


def months(year: int) -> list[str]:
    return [f"{year}-{m:02d}" for m in range(1, 13)]


def _price_ratio(prices: Prices, code: str, period: str, base: str) -> tuple[float, str] | None:
    """P(period) / P(base) for the code or, failing that, its nearest ancestor with both values."""
    for c in [code, *ancestors(code)]:
        series = prices.get(c)
        if series is None:
            continue
        p, p0 = series.get(period), series.get(base)
        if p is not None and p0:
            return p / p0, c
    return None


def link(weights: dict[str, float], prices: Prices, period: str, base: str,
         result: ChainResult | None = None, price_with: PriceWith | None = None) -> float | None:
    """One month's link to the base month, or None if no item could be priced."""
    num = den = total = 0.0
    fallbacks = []
    price_with = price_with or {}
    for code, w in sorted(leaves(weights).items()):
        start = price_with.get(code, code)
        if start == DROP:
            continue
        total += w
        found = _price_ratio(prices, start, period, base)
        if found is None:
            fallbacks.append(Fallback(period, code, None))
            continue
        ratio, used = found
        if used != code:
            fallbacks.append(Fallback(period, code, used))
        num += w * ratio
        den += w
    if den == 0:
        return None  # nothing published for this month (yet): not a month, so nothing to report
    if result is not None:
        result.covered[period] = den / total
        result.fallbacks.extend(fallbacks)
    return num / den


def chain(weights: Weights, prices: Prices | dict[int, Prices], *, first_year: int, last_year: int,
          base_value: float = 100.0, periods: set[str] | None = None,
          by_year: bool = False, price_with: dict[int, PriceWith] | None = None) -> ChainResult:
    """Chain-link years first_year..last_year, starting from base_value in December first_year-1.

    `periods`, if given, limits which months are computed (e.g. the months an
    official series exists for). A year without weights, or without a December
    value, ends the chain: later years can't be linked. With by_year=True,
    `prices` is {year: prices used for that year}. `price_with` is {year: map}.
    """
    result = ChainResult()
    result.index[link_month(first_year)] = base_value
    for year in range(first_year, last_year + 1):
        w = weights.get(year)
        base = link_month(year)
        if not w or base not in result.index:
            break
        year_prices = prices.get(year, {}) if by_year else prices
        year_map = (price_with or {}).get(year)
        for period in months(year):
            if periods is not None and period not in periods:
                continue
            value = link(w, year_prices, period, base, result, year_map)
            if value is None:
                continue
            result.links[period] = value
            result.index[period] = result.index[base] * value
    return result
