"""The Greek CPI's rates: checked against their own index, and against our rebuild.

Two checks, both monthly, both at full precision:

- `own_index`: ELSTAT's table 05 holds the overall index and its twelve-month rate. The rate
  should be the index over the index a year earlier, minus one. Some months are published
  rounded to one decimal (a dull explanation the code recognises); any other gap is a finding.
- `rebuilt`: the twelve-month rate we compute from table 07's overall index (each year's
  levels from its own file, as the site does), against table 05's published rate.

Two rates "agree" when they differ by at most 1e-9 percentage points: both come from the same
published levels, so anything larger means one side changed.
"""

from __future__ import annotations

from traceconomics.engine import rates
from traceconomics.module1 import prices
from traceconomics.module5.record import Check, Comparison, Explanation, explain
from traceconomics.sources.elstat.parse import TOTAL

AGREE = 1e-9            # percentage points; the same rule as the site's official.json
PUBLISHED = "elstat:cpi05"

OWN_INDEX = "gr-cpi-rates-own-index"
REBUILT = "gr-cpi-rates-rebuilt"


def table05(store_con) -> tuple[dict[str, float], dict[str, float]]:
    """Table 05 as the store holds it now: ({"YYYY-MM": index}, {"YYYY-MM": rate in percent})."""
    rows = store_con.execute("""
        SELECT unit, ref_period, value FROM observations
        WHERE dataset = $d AND freq = 'M' AND unit IN ('I20', 'RCH_A_FR')
        QUALIFY row_number() OVER (PARTITION BY key, ref_period ORDER BY published_at DESC, retrieved_at DESC) = 1
            AND status <> 'withdrawn'
        ORDER BY unit, ref_period
    """, {"d": PUBLISHED}).fetchall()
    index = {p: v for u, p, v in rows if u == "I20" and v is not None}
    rate = {p: v * 100 for u, p, v in rows if u == "RCH_A_FR" and v is not None}
    return index, rate


def _label(check: str, period: str, published: float, rebuilt: float,
           explanations: list[Explanation]) -> Comparison:
    if abs(rebuilt - published) <= AGREE:
        return Comparison(period, published, rebuilt, True)
    # Published rounded to one decimal: the rate shown equals ours rounded the same way.
    if abs(published - round(rebuilt, 1)) <= AGREE:
        return Comparison(period, published, rebuilt, False, "rounding")
    e = explain(check, period, explanations)
    if e is None:
        return Comparison(period, published, rebuilt, False, "not-known")
    return Comparison(period, published, rebuilt, False, e.category, e.finding)


def own_index(index: dict[str, float], rate: dict[str, float], explanations: list[Explanation]) -> Check:
    check = Check(OWN_INDEX, "gr", "percent", AGREE,
                  published={"source": PUBLISHED, "reference": "elstat-cpi-rates", "label": "rate"},
                  rebuilt={"source": PUBLISHED, "reference": "elstat-cpi-rates", "label": "index"})
    for period in sorted(rate):
        ours = rates.annual_rate(index, period)
        if ours is not None:
            check.comparisons.append(_label(OWN_INDEX, period, rate[period], ours, explanations))
    return check


def rebuilt(blocks: dict, rate: dict[str, float], explanations: list[Explanation]) -> Check:
    """Ours from table 07's overall index. Each year's levels come from that year's own file;
    the year before's file supplies the year-ago month, as `export.site.official_rate` does."""
    check = Check(REBUILT, "gr", "percent", AGREE,
                  published={"source": PUBLISHED, "reference": "elstat-cpi-rates", "label": "published"},
                  rebuilt={"source": prices.DATASET, "reference": "elstat-cpi-items", "label": "ours"})
    for year in sorted(blocks):
        total = {p: v for y in (year - 1, year) for p, v in blocks.get(y, {}).get(TOTAL, {}).items()
                 if p.startswith(f"{y}-")}
        for period in sorted(p for p in total if p.startswith(f"{year}-")):
            ours = rates.annual_rate(total, period)
            if ours is not None and period in rate:
                check.comparisons.append(_label(REBUILT, period, rate[period], ours, explanations))
    return check


def checks(store_con, explanations: list[Explanation]) -> list[Check]:
    index, rate = table05(store_con)
    return [own_index(index, rate, explanations), rebuilt(prices.cpi_blocks(store_con), rate, explanations)]
