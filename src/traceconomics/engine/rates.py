"""Rates of change from a monthly index, as statistics offices publish them.

All rates are returned as percentages and unrounded. Official practice
(HICP Methodological Manual 2024, section 11.4.6) is to compute rates from
the published, rounded indices and to round rates to one decimal; callers
that need to reproduce a published figure round the index first.
"""

from __future__ import annotations

Index = dict[str, float]  # "YYYY-MM" -> value


def _shift(period: str, months: int) -> str:
    y, m = map(int, period.split("-"))
    n = y * 12 + (m - 1) + months
    return f"{n // 12}-{n % 12 + 1:02d}"


def annual_rate(index: Index, period: str) -> float | None:
    """Change on the same month a year earlier (the headline inflation rate)."""
    prev = index.get(_shift(period, -12))
    cur = index.get(period)
    return None if prev is None or cur is None else (cur / prev - 1) * 100


def monthly_rate(index: Index, period: str) -> float | None:
    """Change on the previous month. Seasonal: neither the CPI nor the HICP is adjusted."""
    prev = index.get(_shift(period, -1))
    cur = index.get(period)
    return None if prev is None or cur is None else (cur / prev - 1) * 100


def annual_average(index: Index, year: int) -> float | None:
    values = [index.get(f"{year}-{m:02d}") for m in range(1, 13)]
    return None if any(v is None for v in values) else sum(values) / 12


def annual_average_rate(index: Index, year: int) -> float | None:
    """Change in the annual average index: Eurostat's annual inflation figure.
    Not the same as the mean of the twelve monthly annual rates."""
    cur, prev = annual_average(index, year), annual_average(index, year - 1)
    return None if cur is None or prev is None else (cur / prev - 1) * 100


def rebase(index: Index, year: int) -> Index:
    """The same index with the average of `year` set to 100. Rates are unchanged."""
    avg = annual_average(index, year)
    if avg is None:
        raise ValueError(f"no complete year {year} to rebase on")
    return {p: v / avg * 100 for p, v in index.items()}
