"""The personal calculator's inputs: everything the browser needs to rebuild a preset's index.

The browser only chains and rebases; every method choice is already made here:

    presets  {group: {year: {division: {pricing code: weight}}}}
             each year's weights, price-updated as the series uses them, summed by the index
             that prices them (the "pricing code": an item's own index, or the ancestor or
             substitute the method prices it with). A month's link is the weighted average of
             price ratios, so summing weights that share a ratio changes nothing, and no cell
             smaller than its pricing code is shipped.
    ratios   {year: {pricing code: [P(month) / P(December before), one per month]}}
             from that year's own price block, with the engine's fallback to the nearest
             ancestor already applied, so the browser never compares index levels across blocks.

A user's own basket keeps each year's mix inside a division and replaces the division shares,
so untouched sliders give back the preset exactly. `rebuild` is the reference for the browser
engine: the export refuses to write a file it can't turn back into the published series.
"""

from __future__ import annotations

from traceconomics.checks import FormatError, require
from traceconomics.engine.chain import DROP, _price_ratio, link_month, months
from traceconomics.engine.rates import rebase
from traceconomics.module1.index import BASE_YEAR, Series

PRESETS = [("all", "all")] + [("B", f"Q{k}") for k in range(1, 6)] + \
          [("tenure", g) for g in ("renter", "owner", "rent_free")] + [("pensioners", g) for g in ("pensioners", "other")]


def _sig(v: float, digits: int) -> float:
    return float(f"{v:.{digits}g}")


def preset_weights(s: Series, years=None) -> dict[str, dict[str, float]]:
    """{year: {pricing code: weight}} for one series (the division is the code's first two digits)."""
    out: dict[str, dict[str, float]] = {}
    for year, u in sorted(s.used.items()):
        if years is not None and year not in years:
            continue
        per: dict[str, float] = {}
        for code, w in u.weights.items():
            start = u.price_with.get(code, code)
            require(start != DROP, f"{year}: a dropped item has a weight")
            require(start[:2] == code[:2], f"{year}: {code} is priced outside its division ({start})")
            per[start] = per.get(start, 0.0) + w
        out[str(year)] = per
    return out


def ratios(series: list[Series], blocks, years=None) -> dict[str, dict[str, list[float | None]]]:
    """{year: {pricing code: monthly ratios to the link month}} for every code the presets use."""
    wanted: dict[int, set[str]] = {}
    for s in series:
        for year, u in s.used.items():
            if years is None or year in years:
                wanted.setdefault(year, set()).update(u.price_with.get(c, c) for c in u.weights)
    out: dict[str, dict[str, list[float | None]]] = {}
    for year, codes in sorted(wanted.items()):
        block, base = blocks[year], link_month(year)
        per = {}
        for code in sorted(codes):
            values = []
            for period in months(year):
                found = _price_ratio(block, code, period, base)
                values.append(None if found is None else found[0])
            while values and values[-1] is None:
                values.pop()                       # months not published yet
            per[code] = values
        out[str(year)] = per
    return out


def rebuild(weights: dict[str, dict[str, float]], ratio: dict[str, dict[str, list]], first_year: int,
            base_year: int = BASE_YEAR) -> dict[str, float]:
    """The index (base_year = 100, unrounded) from calculator inputs: what the browser computes.
    The chain starts at 100 in the December before `first_year`; rebasing removes that level."""
    index = {link_month(first_year): 100.0}
    year = first_year
    while str(year) in weights:
        w, r, base = weights[str(year)], ratio[str(year)], link_month(year)
        n = max(len(r[c]) for c in w)
        for m in range(n):
            num = den = 0.0
            for code in sorted(w):
                v = r[code][m] if m < len(r[code]) else None
                if v is None:
                    continue
                num += w[code] * v
                den += w[code]
            if den:
                index[months(year)[m]] = index[base] * num / den
        year += 1
    return rebase(index, base_year)


def compact(weights: dict, ratio: dict) -> dict:
    """The file layout: one list of pricing codes, then arrays that refer to it by position."""
    codes = sorted({c for per in ratio.values() for c in per})
    pos = {c: i for i, c in enumerate(codes)}
    return {"codes": codes,
            "ratios": {y: [[pos[c], vals] for c, vals in sorted(per.items())] for y, per in ratio.items()},
            "presets": {k: {y: [[pos[c], w] for c, w in sorted(per.items())] for y, per in yrs.items()}
                        for k, yrs in weights.items()}}


# The calculator covers the recent years a person compares their own inflation with (from 2019:
# the pandemic and the 2022 energy shock); the charts carry every group's full history. A longer
# window only costs download size (about 0.2 MB compressed from 2019, 0.5 MB from 2009).
FIRST_YEAR = 2019


def build_checked(series: list[Series], blocks, first_year: int = FIRST_YEAR) -> dict:
    """The smallest number of significant digits (from 8) whose file rebuilds every preset exactly."""
    last = None
    for digits in range(8, 16):
        try:
            return build(series, blocks, first_year, digits)
        except FormatError as e:    # a month that rounds the other way: try more digits
            last = e
    raise last


def build(series: list[Series], blocks, first_year: int | None = None, digits: int = 8) -> dict:
    """The calculator file, checked: every preset, rebuilt from the file's own (rounded) numbers,
    must give back its published index to the last digit from `first_year` on."""
    by = {(s.grouping, s.group): s for s in series}
    first_year = first_year or min(by[PRESETS[0]].used)
    years = {y for y in by[PRESETS[0]].used if y >= first_year}
    weights = {f"{g}/{q}": {y: {c: _sig(w, digits) for c, w in per.items()}
                            for y, per in preset_weights(by[(g, q)], years).items()} for g, q in PRESETS}
    ratio = {y: {c: [None if v is None else _sig(v, digits) for v in vals] for c, vals in per.items()}
             for y, per in ratios([by[p] for p in PRESETS], blocks, years).items()}
    for g, q in PRESETS:
        s = by[(g, q)]
        got = {p: round(v, 2) for p, v in rebuild(weights[f"{g}/{q}"], ratio, first_year).items()}
        bad = [p for p in got if p >= f"{first_year}-01" and got[p] != s.published.get(p)]
        require(not bad, f"calculator inputs for {g}/{q} don't rebuild the published index: {bad[:3]}")
    return {"base_year": BASE_YEAR, "first_year": first_year, "digits": digits, **compact(weights, ratio)}
