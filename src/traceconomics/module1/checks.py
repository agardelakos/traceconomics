"""Checks of module 1 against the official CPI (V3).

V3 is a ladder that changes one thing at a time, so each difference has one cause:

    L0  the official CPI (which the engine rebuilds exactly from ELSTAT's own weights: V1-CPI)
    L1  our all-households weights from the survey microdata, with ELSTAT's own timing (survey
        y-2, price-updated to December y-1): L1 - L0 is the weights data (the public use file
        against ELSTAT's full survey; the items the file leaves out; our mapping of old codes)
    L2  the same with our timing rule (Rule N: survey y-1): L2 - L1 is the timing rule

Annual-average rates; a year where L1 differs from L0 by more than REPORT_PP is listed for an
explanation. Report only: no pass or fail (the margin is tier C).
"""

from __future__ import annotations

from dataclasses import dataclass

from traceconomics.engine.rates import annual_average_rate
from traceconomics.module1 import index
from traceconomics.module1.prices import cpi_blocks
from traceconomics.module1.schedule import elstat_rule, rule_n
from traceconomics.module1.weights_used import load_baskets

REPORT_PP = 0.2
FIRST_L1 = 2012
# Found by item-level attribution on 2026-10-19 (December-on-December links, our weights against
# the CPI's table 07 weights): ELSTAT's CPI weights air transport (07.3.3) at 4-20 per mille, the
# survey at 1-3; air fares swing by 20-50% a year. Tolls (07.2.4.2) are 10-14 per mille in the
# CPI and about 1 in the public use file, which cuts them.
EXPLAINED = {
    2014: ("the 2013 months come from ELSTAT's fixed-basket years; transport: tolls (12.1 per mille in the CPI, "
           "cut from the survey) and combined transport (6.5, +10.6%) weigh more in the CPI, fuels (-10.8%) in ours"),
    2017: "transport: air fares +22% (Dec/Dec) at 19.8 per mille in the CPI against 3.2 in the survey; tolls cut",
    2020: "transport: air fares -26% at 16.6 per mille in the CPI against 3.4 in the survey; tolls cut",
    2021: "housing: the survey weights natural gas (+136%) and heating oil (+34%) above ELSTAT's 2021 weights",
    2023: "ELSTAT's 2023 weights fit survey 2022 (t-1), not survey 2021: the timing column brings it back",
    2024: "transport: air fares +48% at 11.4 per mille in the CPI against 1.3 in the survey; tolls cut",
    2025: "transport: air fares +12% at 19.4 per mille in the CPI against 2.4 in the survey; tolls cut",
}
# Known before the run: reasons L1 can't match L0 in these years.
KNOWN = {
    2011: "ELSTAT's CPI was a fixed basket in 2011-2013, not re-weighted each December",
    2012: "ELSTAT's CPI was a fixed basket in 2011-2013, not re-weighted each December",
    2013: "ELSTAT's CPI was a fixed basket in 2011-2013, not re-weighted each December",
    2022: "ELSTAT's 2022 weights match no single survey (survey 2020 moved forward with national accounts, inferred)",
}


@dataclass
class V3Row:
    year: int
    official: float
    l1: float
    l2: float

    @property
    def weights_effect(self) -> float:
        return self.l1 - self.official

    @property
    def timing_effect(self) -> float:
        return self.l2 - self.l1


def v3(con, archive, spending: str = "purchases") -> list[V3Row]:
    blocks = index.price_blocks(con, archive)
    baskets = load_baskets(con, spending=spending)
    # ELSTAT's rule needs survey y-2's average prices: from 2012 (survey 2010), the first CPI year.
    l1 = index.build(con, "all", "all", spending=spending, blocks=blocks, baskets=baskets, rule=elstat_rule,
                     first_year=FIRST_L1)
    l2 = index.build(con, "all", "all", spending=spending, blocks=blocks, baskets=baskets, rule=rule_n)
    official: dict[str, float] = {}
    for year, block in blocks.items():
        for period, v in block.get("TOTAL", {}).items():
            if period[:4] == str(year):
                official[period] = v
    rows = []
    for y in range(FIRST_L1 + 1, max(blocks) + 1):
        o = annual_average_rate(official, y)
        a, b = annual_average_rate(l1.index, y), annual_average_rate(l2.index, y)
        if None not in (o, a, b):
            rows.append(V3Row(y, o, a, b))
    return rows


# -- V6: our contributions code against Eurostat's own euro-area contributions -------------------

@dataclass
class V6Result:
    compared: int
    exact: int                    # equal at two decimals
    worst: tuple[str, str, float, float] | None    # period, division, ours, Eurostat


def v6(con, archive, first_year: int = 2016, last_year: int = 2025) -> V6Result:
    """Rebuild Eurostat's contributions of the 12 ECOICOP v1 divisions to the euro area's annual
    HICP rate (dataset prc_hicp_ctrb) with our `ribe` code, from Eurostat's euro-area division
    indices (prc_hicp_midx) and item weights (prc_hicp_inw)."""
    import gzip

    from traceconomics.checks import require
    from traceconomics.engine import chain
    from traceconomics.module1.contributions import ribe
    from traceconomics.module1.schedule import FINAL, Entry
    from traceconomics.module1.weights_used import Used
    from traceconomics.store.query import as_of

    prices: dict[str, dict[str, float]] = {}
    for code, period, value in as_of(con, "eurostat:prc_hicp_midx", where="geo = 'EA' AND unit = 'I15'") \
            .project("coicop, ref_period, value").fetchall():
        if value is not None and code.isdigit() and len(code) == 2:
            prices.setdefault(code, {})[period] = value
    weights: dict[int, dict[str, float]] = {}
    for code, year, value in as_of(con, "eurostat:prc_hicp_inw", where="geo = 'EA'") \
            .project("coicop, ref_period, value").fetchall():
        if value and code.isdigit() and len(code) == 2:
            weights.setdefault(int(year), {})[code] = value
    years = range(first_year - 1, last_year + 1)
    chained = chain(weights, prices, first_year=first_year - 1, last_year=last_year)
    used = {y: Used(Entry(y, y, FINAL, f"{y}-01", "Eurostat weights"),
                    {c: w / sum(weights[y].values()) for c, w in weights[y].items()}, {}) for y in years}
    series = index.Series("EA", "all", "hicp", [], used, chained)
    ours = ribe(series, {y: prices for y in years})

    rec = archive.latest("eurostat", "prc_hicp_ctrb")
    require(rec is not None, "no archived prc_hicp_ctrb; import it first")
    lines = gzip.decompress((archive.root / rec["path"]).read_bytes()).decode("utf-8").splitlines()
    head = [h.strip() for h in lines[0].split("\t")[1:]]
    official: dict[tuple[str, str], float] = {}
    for line in lines[1:]:
        key, *cells = line.split("\t")
        _, unit, coicop, geo = key.split(",")
        if unit != "PC_PNT" or geo != "EA" or len(coicop) != 4:
            continue
        for period, cell in zip(head, cells):
            text = cell.strip().split(" ")[0]
            if text and text != ":":
                official[(period, coicop[2:])] = float(text)
    compared = exact = 0
    worst = None
    for period, parts in ours.items():
        if not (f"{first_year}-01" <= period <= f"{last_year}-12"):
            continue
        for h, v in parts.items():
            o = official.get((period, h))
            if o is None:
                continue
            compared += 1
            gap = abs(round(v, 2) - o)
            exact += gap < 0.005
            if worst is None or gap > abs(round(worst[2], 2) - worst[3]):
                worst = (period, h, v, o)
    return V6Result(compared, exact, worst)


# -- V-prices: the CPI's item indices against the HICP's, which ELSTAT says use the same prices ---

def v_prices(con, digits=(4, 5)) -> dict[int, dict]:
    """Per year: how far apart the CPI's and the HICP's annual rates are for the same item code
    (both are re-coded series in COICOP 2018: ELSTAT's re-issued table 07, Eurostat's back-cast).
    Report only: the two use the same prices but weight them differently inside an item."""
    import statistics

    from traceconomics.engine.rates import annual_rate
    from traceconomics.store.query import as_of

    blocks = cpi_blocks(con)
    cpi: dict[str, dict[str, float]] = {}
    for year, block in blocks.items():
        for code, series in block.items():
            for p, v in series.items():
                if p[:4] == str(year):
                    cpi.setdefault(code, {})[p] = v
    hicp: dict[str, dict[str, float]] = {}
    for code, p, v in as_of(con, "eurostat:prc_hicp_minr", where="geo = 'GR' AND unit = 'I25'") \
            .project("coicop18, ref_period, value").fetchall():
        if v is not None and code.isdigit() and len(code) in digits:
            hicp.setdefault(code, {})[p] = v
    out: dict[int, dict] = {}
    for code in sorted(set(cpi) & set(hicp)):
        for p in cpi[code]:
            a, b = annual_rate(cpi[code], p), annual_rate(hicp[code], p)
            if a is None or b is None:
                continue
            out.setdefault(int(p[:4]), {}).setdefault("gaps", []).append((abs(a - b), code))
    for year, d in out.items():
        gaps = [g for g, _ in d.pop("gaps")] if "gaps" in d else []
        d.update({"pairs": len(gaps), "median": statistics.median(gaps), "within_0.1": sum(g <= 0.1 for g in gaps) / len(gaps),
                  "max": max(gaps)})
    return dict(sorted(out.items()))


# -- The seam between ELSTAT's original and re-issued prices (2010) ------------------------------

def seam(con, archive) -> dict[str, tuple[float, float]]:
    """{group: (Jan-to-Dec 2010 movement with the original prices, with the re-issued ones)}, in %.

    The same 2010 weights priced both ways: the only year where both versions of ELSTAT's item
    data exist, so the difference measures what using the older version for 2009-2010 can do."""
    from traceconomics.engine.chain import link

    reissued = cpi_blocks(con)[2010]
    out = {}
    for s in index.build_all(con, archive):
        u = s.used[2010]
        blocks = index.price_blocks(con, archive)
        a = link(u.weights, blocks[2010], "2010-12", "2010-01", price_with=u.price_with)
        b = link(u.weights, reissued, "2010-12", "2010-01", price_with=u.price_with)
        out[f"{s.grouping}/{s.group}"] = ((a - 1) * 100, (b - 1) * 100)
    return out
