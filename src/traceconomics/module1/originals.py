"""CPI prices for 2008-2010 from ELSTAT's original (pre-recode) tables, in COICOP 2018 codes.

ELSTAT's re-issued table 07 starts in 2010-01, so it can't link 2010 to December 2009, nor
price-update weights with 2008 or 2009 prices. The original tables can: they hold each item's
monthly index in ELSTAT's old code list (ECOICOP version 1 subclasses, some split into 6-digit
items).

- All three years are put on one base, 2009 = 100: the 2008 and 2010 files are on it already;
  the 2009 file (base 2005) is divided by each item's 2009 average. With that, the files give
  ELSTAT's published annual rates for every month of 2009 and 2010 exactly.
- 2009 and 2010 become blocks of movements since the previous December (each code at 100 in
  December of the year before), the form the engine links. 2008 becomes a block of levels with
  each item's 2008 average at 100, enough to price-update survey-2008 weights.
- The old item numbers are national, not ECOICOP v1's: the same number can mean something else
  (07221 is "car fuels" and 07222 "lubricants" in the old list; in ECOICOP v1 they are diesel and
  petrol). The 4-digit classes are the COICOP classes (their 2010 movements match the re-issued
  series within 0.5 pp for 43 of the 56 classes both have, within 2 pp for 52). So the bridge is
  at class level: every ECOICOP v1 subclass takes its class's movement from the old table (or
  its group's, or division's, where ELSTAT published no class row), and is carried to COICOP
  2018 with the same table the survey weights use. A COICOP 2018 code's movement is the weighted
  mean of the subclasses that map into it (each class's weight shared equally by its subclasses,
  times the mapping share). Every parent level is built the same way, so the engine can fall back
  to a parent as it does with the re-issued series. Within a class, 2009 and 2010 therefore have
  no finer detail.

These are an older version of ELSTAT's prices than the re-issued series used from 2011: the
re-issue recomputed 2010 rather than re-coding it (`seam` measures the difference).
"""

from __future__ import annotations

from traceconomics.checks import require
from traceconomics.engine.chain import Prices, link_month, months
from traceconomics.local.mapping import V1_TO_2018, load
from traceconomics.sources.elstat.original07 import TOTAL, Original07, parse

YEARS = (2008, 2009, 2010)
BASE_YEAR = "2009"


def read(archive) -> dict[int, Original07]:
    out = {}
    for year in YEARS:
        rec = archive.latest("elstat", f"cpi07-original-{year}")
        require(rec is not None, f"no archived original table 07 for {year} (elstat/cpi07-original-{year})")
        out[year] = parse(archive.root / rec["path"], year)
    return out


def on_base_2009(tables: dict[int, Original07]) -> dict[int, dict[str, dict[str, float]]]:
    """{year: {old code: {"YYYY-MM": index on 2009 = 100}}}."""
    out = {}
    for year, t in tables.items():
        series = {}
        for code, values in t.months.items():
            if t.base == BASE_YEAR:
                scale = 1.0
            else:
                require(year == int(BASE_YEAR), f"{year}: base {t.base} can only be converted in {BASE_YEAR}")
                avg = t.average.get(code)
                if not avg:
                    continue
                scale = 100.0 / avg
            series[code] = {p: v * scale for p, v in zip(months(year), values) if v}
        out[year] = series
    return out


def _row_for(v1: str, t: Original07, previous=None, base: str | None = None) -> str | None:
    """The old table's row that prices an ECOICOP v1 subclass: its class, else its group, else its
    division; with `previous`, the first that also has last year's December to link to."""
    for k in (4, 3, 2):
        code = v1[:k]
        if code in t.months and t.weights.get(code):
            if previous is None or previous.get(code, {}).get(base):
                return code
    return None


def _value(series: dict[str, dict[str, float]], code: str, period: str) -> float | None:
    v = series.get(code, {}).get(period)
    return v or None


def to_2018(t: Original07, levels: dict[str, dict[str, float]], previous: dict[str, dict[str, float]] | None,
            year: int) -> tuple[Prices, list[str]]:
    """One year's block in COICOP 2018 codes (all levels), and the v1 subclasses that couldn't be priced.

    With `previous` (last year's levels, same base): movements since December of the year
    before, December = 100. Without: levels with each row's own yearly average at 100."""
    table = load(V1_TO_2018)
    shares: dict[str, list[tuple[str, float]]] = {}
    for row in table.itertuples():
        if row.share > 0:                     # a few RAS splits round to exactly 0: they carry nothing
            shares.setdefault(row.from_code, []).append((row.to_code, row.share))
    base = link_month(year)
    rows = {v1: _row_for(v1, t, previous, base) for v1 in shares}
    per_row: dict[str, int] = {}
    for r in rows.values():
        if r is not None:
            per_row[r] = per_row.get(r, 0) + 1
    num: dict[str, dict[str, float]] = {}
    den: dict[str, float] = {}
    lost = []
    for v1, r in sorted(rows.items()):
        series = levels.get(r) if r else None
        if not series:
            lost.append(v1)
            continue
        if previous is not None:
            start = _value(previous, r, base)
            if start is None:
                lost.append(v1)
                continue
            rel = {p: v / start for p, v in series.items()}
        else:
            avg = sum(series.values()) / len(series)
            rel = {p: v / avg for p, v in series.items()}
        for target, share in shares[v1]:
            w = t.weights[r] / per_row[r] * share
            for code in {target[:k] for k in range(2, len(target) + 1)}:
                den[code] = den.get(code, 0.0) + w
                for p, x in rel.items():
                    num.setdefault(code, {})[p] = num.get(code, {}).get(p, 0.0) + w * x
    block: Prices = {}
    for code, values in num.items():
        block[code] = {p: 100.0 * v / den[code] for p, v in values.items()}
        if previous is not None:
            block[code][base] = 100.0
    return block, lost


def blocks(archive) -> tuple[dict[int, Prices], dict[int, list[str]]]:
    """({2008: levels block, 2009: block, 2010: block}, {year: v1 subclasses not priced})."""
    tables = read(archive)
    levels = on_base_2009(tables)
    out, lost = {}, {}
    out[2008], lost[2008] = to_2018(tables[2008], levels[2008], None, 2008)
    for year in (2009, 2010):
        out[year], lost[year] = to_2018(tables[year], levels[year], levels[year - 1], year)
    return out, lost
