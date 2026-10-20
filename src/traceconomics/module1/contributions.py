"""How much each division adds to a group's annual rate: Eurostat's additive (Ribe) contributions.

HICP Methodological Manual 2024, section 8.6.3, equation 8.42. For month m of year t, with P the
group's index and P_H the group's own index for division H (its leaves, its weights):

    this-year term  TYT_H = P(Dec t-1 / m, t-1) * (P_H(m t / Dec t-1) - 1) * w_H(t)
    last-year term  LYT_H = (P_H(Dec t-1 / m, t-1) - 1) * w_H(t-1, price-updated to m of t-1)

where the last-year weight is w_H(t-1) * P_H(m t-1 / Dec t-2) / P(m t-1 / Dec t-2) (equation
8.4c). The contributions of all divisions add up to the annual rate exactly (by construction);
they are computed from unrounded data and shown with two decimals, as Eurostat does.

Sub-indices are the group's own, not the CPI's published division indices: only the group's own
weights and leaves make the parts add up to the group's rate.
"""

from __future__ import annotations

from traceconomics.engine.chain import Prices, _price_ratio, link_month
from traceconomics.module1.index import Series


def division_links(series: Series, blocks: dict[int, Prices], digits: int = 2) -> dict[int, dict[str, dict]]:
    """{year: {division: {"w": weight, "links": {period: link to Dec of year-1}}}}."""
    out: dict[int, dict[str, dict]] = {}
    for year, used in series.used.items():
        block = blocks.get(year, {})
        base = link_month(year)
        parts: dict[str, dict] = {}
        for code, w in used.weights.items():
            d = parts.setdefault(code[:digits], {"w": 0.0, "num": {}})
            d["w"] += w
            start = used.price_with.get(code, code)
            for period in series.chained.links:
                if period[:4] != str(year):
                    continue
                found = _price_ratio(block, start, period, base)
                if found is not None:
                    d["num"][period] = d["num"].get(period, 0.0) + w * found[0]
        out[year] = {h: {"w": d["w"], "links": {p: n / d["w"] for p, n in d["num"].items()}} for h, d in parts.items()}
    return out


def ribe(series: Series, blocks: dict[int, Prices], digits: int = 2) -> dict[str, dict[str, float]]:
    """{period: {division: contribution in percentage points}} for every month with an annual rate."""
    subs = division_links(series, blocks, digits)
    total = series.chained.links
    out: dict[str, dict[str, float]] = {}
    for period, link_t in sorted(total.items()):
        year, month = int(period[:4]), period[5:]
        prev = f"{year - 1}-{month}"
        dec_prev = f"{year - 1}-12"
        if month == "12":
            # December (equation 8.42a): the last-year term is zero and the factor is 1.
            out[period] = {h: (sub["links"][period] - 1) * sub["w"] * 100 for h, sub in subs[year].items()}
            continue
        if year - 1 not in subs or prev not in total or dec_prev not in total:
            continue
        # The group's own index from month m of t-1 to December t-1.
        p_m_dec = total[dec_prev] / total[prev]
        contrib = {}
        for h in set(subs[year]) | set(subs[year - 1]):
            tyt = 0.0
            if h in subs[year]:
                tyt = p_m_dec * (subs[year][h]["links"][period] - 1) * subs[year][h]["w"]
            lyt = 0.0
            if h in subs[year - 1]:
                sub = subs[year - 1][h]
                w_m = sub["w"] * sub["links"][prev] / total[prev]                 # equation 8.4c
                lyt = (sub["links"][dec_prev] / sub["links"][prev] - 1) * w_m
            contrib[h] = (tyt + lyt) * 100
        out[period] = contrib
    return out
