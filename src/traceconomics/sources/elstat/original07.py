"""Read ELSTAT's original (pre-recode) CPI table VII, as published for 2008-2010 (Greek files).

Before the 2026 re-issue in COICOP 2018, table VII listed the year's monthly index for every item
in ELSTAT's old national code list (ECOICOP version 1 subclasses, a few split into 6-digit
items), with the item weights and the annual average. Layout:

    row 0   title, naming the base ("Έτος βάσης : 2009=100,0")
    row 2   headers: codes | items | weights (per mille) | 1 ... 12 | annual average ("ΜΕΣΟΣ")
    then    item rows; division headings without numbers; the overall index on a row labelled
            "Γ.Δ.Τ.Κ." (or "ΓΕΝΙΚΟΣ ...") with no code

The files survive in the Wayback Machine's copy of ELSTAT's old site; the archive keeps them as
`elstat/cpi07-original-YYYY`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import xlrd

from traceconomics.checks import require

CODE = re.compile(r"^\d{2,7}$")
BASE = re.compile(r"(\d{4})\s*=\s*100")
TOTAL = "TOTAL"


@dataclass
class Original07:
    year: int
    base: str                                          # e.g. "2009"
    weights: dict[str, float] = field(default_factory=dict)   # per mille
    months: dict[str, list[float]] = field(default_factory=dict)   # code -> 12 monthly values
    average: dict[str, float] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)


def _code(value) -> str:
    if isinstance(value, float):
        value = str(int(value))
    return str(value).strip()


def parse(path: Path, year: int) -> Original07:
    sheet = xlrd.open_workbook(path).sheet_by_index(0)
    title = " ".join(str(sheet.cell_value(0, c)) for c in range(sheet.ncols))
    m = BASE.search(title)
    require(m is not None, f"{Path(path).name}: no base year in the title")
    require(str(year) in title, f"{Path(path).name}: the title doesn't name {year}")
    t = Original07(year, m.group(1))
    for r in range(sheet.nrows):
        values = [sheet.cell_value(r, c) for c in range(3, 16)]
        if not all(isinstance(v, float) for v in values):
            continue
        code, label = _code(sheet.cell_value(r, 0)), str(sheet.cell_value(r, 1)).strip()
        if CODE.match(code):
            key = code
        elif label.replace(".", "").replace(" ", "").upper() == "ΓΔΤΚ" or "ΓΕΝΙΚΟΣ" in label.upper():
            key = TOTAL
        else:
            continue
        if key in t.months:
            continue                                   # summary blocks repeat the divisions
        w = sheet.cell_value(r, 2)
        if isinstance(w, float):
            t.weights[key] = w
        t.months[key] = values[:12]
        t.average[key] = values[12]
        t.labels[key] = label
    require(TOTAL in t.months, f"{Path(path).name}: no overall index row")
    require(len(t.months) > 150, f"{Path(path).name}: only {len(t.months)} rows")
    return t
