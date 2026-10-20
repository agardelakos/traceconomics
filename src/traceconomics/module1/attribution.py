"""V5: our default series against Bruegel's, one setting at a time (tier C: report and explain).

The Q1-Q5 gap in annual averages, rung by rung:

  Bruegel's side (ECOICOP v1 HICP, Eurostat HBS 2020 weights at 3 digits, fixed):
    B0  Bruegel as published
    B1  the same weights, chained at December instead of a weighted sum of year-on-year rates
  Our side (COICOP 2018):
    O3  our survey-2020 weights at 3 digits, fixed, HICP prices, chained
    O2  our weights for each year (Rule N), 3 digits, HICP prices
    O1  the same at the finest detail
    O0  our default: the same with CPI prices

B1 -> O3 is the weights themselves: Eurostat's published quintile structure against our microdata
shares for the same survey (and the classification's change from ECOICOP v1 to COICOP 2018,
which can't be separated from it). Each other step changes one setting.
"""

from __future__ import annotations

from traceconomics.engine import chain
from traceconomics.engine.rates import annual_average_rate
from traceconomics.module1 import benchmarks, index
from traceconomics.module1.prices import hicp_blocks
from traceconomics.module1.schedule import FINAL, Entry, rule_n
from traceconomics.module1.weights_used import Basket, load_baskets
from traceconomics.store.query import as_of

YEARS = range(2020, 2024)       # whole years Bruegel covers with final data (2019 needs 2018)


def _same_year(years, surveys, release_dates=None):
    return [Entry(y, y, FINAL, f"{y}-01", "fixed weights, not price-updated") for y in years if y in surveys]


def at_level(baskets: dict, digits: int) -> dict:
    return {k: Basket({c: s for c, s in b.shares.items() if len(c) == digits},
                      {c: r for c, r in b.reliability.items() if len(c) == digits}) for k, b in baskets.items()}


def gap(q1, q5) -> dict[int, float]:
    a, b = q1.annual_average_rates(), q5.annual_average_rates()
    return {y: a[y] - b[y] for y in YEARS if y in a and y in b}


def v5_bruegel(con, archive) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    # B0: Bruegel as published (annual means of its monthly rates).
    pub = benchmarks.bruegel_published(archive)
    out["B0 Bruegel as published"] = {y: sum(pub["QU1"][f"{y}-{m:02d}"] - pub["QU5"][f"{y}-{m:02d}"]
                                             for m in range(1, 13)) / 12 for y in YEARS}
    # B1: Bruegel's weights and prices, chained.
    prices_v1: dict[str, dict[str, float]] = {}
    for code, period, value in as_of(con, "eurostat:prc_hicp_midx", where="geo = 'GR' AND unit = 'I15'") \
            .project("coicop, ref_period, value").fetchall():
        if value is not None and code.isdigit() and len(code) in (2, 3):
            prices_v1.setdefault(code, {})[period] = value
    structure = benchmarks.hbs_structure(archive)
    chained = {}
    for q in ("QU1", "QU5"):
        w = {}
        for code, v in structure[q].items():
            if code.startswith("042") or not v:
                continue
            target = code if code in prices_v1 else code[:2]
            if target in prices_v1:
                w[target] = w.get(target, 0.0) + v
        r = chain({y: w for y in range(2019, 2025)}, prices_v1, first_year=2019, last_year=2024)
        chained[q] = r.index
    out["B1 Bruegel weights, chained"] = {y: annual_average_rate(chained["QU1"], y) - annual_average_rate(chained["QU5"], y)
                                         for y in YEARS}
    # Our side.
    baskets = load_baskets(con, spending="purchases")
    years = range(2019, 2027)          # through the newest prices, as every series is rebased on 2025
    hicp = hicp_blocks(con)
    fixed = {(y, g, label): baskets[(2020, g, label)] for y in years for g, label in (("B", "Q1"), ("B", "Q5"))}

    def pair(**kw):
        return gap(*(index.build(None, "B", q, **kw) for q in ("Q1", "Q5")))

    out["O3 our survey-2020 weights, 3 digits, fixed, HICP"] = pair(blocks=hicp, baskets=at_level(fixed, 3),
                                                                   rule=_same_year, first_year=2019)
    out["O2 our weights each year (Rule N), 3 digits, HICP"] = pair(blocks=hicp, baskets=at_level(baskets, 3),
                                                                   rule=rule_n)
    out["O1 the same, finest detail, HICP"] = pair(blocks=hicp, baskets=baskets, rule=rule_n)
    out["O0 our default (CPI prices)"] = pair(blocks=index.price_blocks(con, archive), baskets=baskets, rule=rule_n)
    return out


def v5_kepe(con, archive) -> dict[str, dict[int, float]]:
    """Our default against KEPE (P20 - R20 gap), one setting at a time. K1 is our rebuild of KEPE's
    settings (V4: close but not exact: KEPE priced the 12 COICOP 1999 divisions as published then,
    we only have ELSTAT's re-issued COICOP 2018 series)."""
    years = range(2021, 2025)
    pub = benchmarks.kepe_published()["chart1"]
    out = {"K0 KEPE as published": {y: pub["P20"][str(y)] - pub["R20"][str(y)] for y in years}}
    blocks = index.price_blocks(con, archive)
    baskets = load_baskets(con, spending="purchases")

    def pair(**kw):
        a, b = (index.build(None, "B", q, **kw) for q in ("Q1", "Q5"))
        ra, rb = a.annual_average_rates(), b.annual_average_rates()
        return {y: ra[y] - rb[y] for y in years if y in ra and y in rb}

    out["K1 KEPE's settings (same-year weights, divisions)"] = pair(
        blocks=blocks, baskets=benchmarks.divisions_only(baskets), rule=benchmarks.kepe_rule, first_year=2016)
    out["K2 our timing (Rule N), divisions"] = pair(blocks=blocks, baskets=benchmarks.divisions_only(baskets), rule=rule_n)
    out["K3 our default (finest detail)"] = pair(blocks=blocks, baskets=baskets, rule=rule_n)
    return out
