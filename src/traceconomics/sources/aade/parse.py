"""AADE's yearly personal income tax statistics: table 1 (Π1), the all-regions totals.

Table 1 has one block of columns per region, each with three columns (per return, taxpayer,
spouse), and a last block "Σύνολο Περιφεριών" (all regions). We read only that block's "per
return" column ("Δήλωση"): AADE's own national totals, as published. AADE's terms forbid
modifying its information, so nothing here adds regions up or rescales a figure; the text of
each value is kept as the file holds it.

The layout checked is that of tax years 2019 to 2022 (workbooks published 2021-2024); anything
else is refused, never guessed.
"""

from __future__ import annotations

import re
from pathlib import Path

import openpyxl

from traceconomics.checks import FormatError, require

PARSER_VERSION = "1"
SHEET = "Π1"
ALL_REGIONS = "Σύνολο Περιφεριών"
PER_RETURN = "Δήλωση"
YEAR = re.compile(r"^Φορολογικό Έτος (\d{4})$")

# Table 1's rows we keep, by their label as AADE writes it, and the code each gets here.
MEASURES = {
    "1.ΑΡΙΘΜΟΣ ΦΟΡΟΛΟΓΟΥΜΕΝΩΝ": "returns",
    "2.ΔΗΛΩΘΕΝ ΕΙΣΟΔΗΜΑ": "declared_income",
    "ΑΠΟ ΑΚΙΝΗΤΗ ΠΕΡΙΟΥΣΙΑ": "declared_income_property",
    "ΑΠΟ ΜΕΡΙΣΜΑΤΑ-ΤΟΚΟΥΣ-ΔΙΚΑΙΩΜΑΤΑ ΚΑΙ ΥΠΕΡΑΞΙΑ ΑΠΟ ΜΕΤΑΒΙΒΑΣΗ ΚΕΦΑΛΑΙΟΥ": "declared_income_capital",
    "ΑΠΟ ΕΠΙΧΕΙΡΗΜΑΤΙΚΗ ΔΡΑΣΤΗΡΙΟΤΗΤΑ": "declared_income_business",
    "ΑΠΟ ΑΓΡΟΤΙΚΗ ΕΠΙΧΕΙΡΗΜΑΤΙΚΗ ΔΡΑΣΤΗΡΙΟΤΗΤΑ": "declared_income_farming",
    "ΑΠΟ ΜΙΣΘΩΤΕΣ ΥΠΗΡΕΣΙΕΣ ΚΑΙ ΝΑΥΤΙΚΟ ΕΙΣΟΔΗΜΑ": "declared_income_employment",
}
UNITS = {"returns": "NR"}  # every other measure is in euros


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def rows(path: Path) -> list[tuple[str, str, str, str, float]]:
    """(measure, unit, ref_period, value_text, value) for each kept row of table 1, all regions."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        require(SHEET in wb.sheetnames, f"{Path(path).name}: no sheet {SHEET!r} (sheets: {wb.sheetnames[:6]})")
        table = [tuple(_text(c) for c in r) for r in wb[SHEET].iter_rows(values_only=True)]
    finally:
        wb.close()
    years = [m.group(1) for r in table for c in r if (m := YEAR.match(c))]
    require(len(set(years)) == 1, f"{Path(path).name}: expected one 'Φορολογικό Έτος YYYY', found {sorted(set(years))}")
    heads = [i for i, r in enumerate(table) if r and r[0] == "Μετρήσιμο - Περιγραφή"]
    require(
        len(heads) == 1 and heads[0] > 0,
        f"{Path(path).name}: the header row 'Μετρήσιμο - Περιγραφή' isn't where expected",
    )
    regions, sub = table[heads[0] - 1], table[heads[0]]
    require(len(regions) == len(sub), f"{Path(path).name}: the two header rows differ in length")
    cols = [i for i, (g, s) in enumerate(zip(regions, sub, strict=True)) if g == ALL_REGIONS and s == PER_RETURN]
    require(
        len(cols) == 1, f"{Path(path).name}: expected one '{ALL_REGIONS}' / '{PER_RETURN}' column, found {len(cols)}"
    )
    col = cols[0]
    found: dict[str, tuple[str, float]] = {}
    for r in table[heads[0] + 1 :]:
        label = r[0] if r else ""
        if label in MEASURES and MEASURES[label] not in found:
            text = r[col] if col < len(r) else ""
            try:
                value = float(text)
            except ValueError:
                raise FormatError(f"{Path(path).name}: {label!r} all regions is {text!r}, not a number") from None
            found[MEASURES[label]] = (text, value)
    missing = sorted(set(MEASURES.values()) - set(found))
    require(not missing, f"{Path(path).name}: rows missing from table 1: {missing}")
    return [(m, UNITS.get(m, "EUR"), years[0], text, value) for m, (text, value) in sorted(found.items())]
