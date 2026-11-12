"""EU-SILC public use files: tenure and rent paid, by household and by person.

The consistency topic asks "what share of households rent?" and "how much rent do households
pay?" of several sources. Eurostat publishes SILC's tenure only by persons (`ilc_lvho02`) and no
rent amounts, so the household figures come from ELSTAT's SILC public use files, read here in
memory (the microdata are never unpacked to disk, published or synced: `archive.local_only`).

Per survey year, one table, archived as `oet-local/silc-tenure-gr-YYYY`: for all households,
owners, renters (market and reduced rent together, and each apart) and the housed free:
households counted and weighted (`DB090`), people weighted (`RB050`), and the rent paid in euros
a year.

What the file holds (ELSTAT's variable list for 2024, H file): `HH021` tenure status, 1 owner
without mortgage, 2 owner with mortgage, 3 tenant at market rent, 4 rented at a reduced rate,
5 rent-free; `HH060` "current rent related to occupied dwelling". The list gives no period for
`HH060`; Eurostat's SILC guidelines define it as monthly, and the amounts agree (a mean near
€350 among renters in 2024, against the household budget survey's €376 a month), so the yearly
total is twelve times the weighted sum. ELSTAT's own statement of the period is UNVERIFIED.
SILC asks about tenure and rent at the time of the interview, so a SILC year's figures belong to
that year (its incomes, by contrast, are the year before's).

Layouts read (checked 2026-11-08 on every file 2003-2025): one workbook "... Public Use
Files.xlsx" with sheets D_FILE, H_FILE and R_FILE (from 2020) or D-FILE, H-FILE and R-FILE
(2003-2017). Tenure is `HH021` from 2010; 2003-2009 have only the older `HH020`, whose codes
ELSTAT's description of the 2008 and 2010 files gives as 1 owner, 2 tenant at market rent,
3 rented at a reduced rate, 4 rent-free (2010 holds both). The 2018 and 2019 files hold their
data as .xlsb (Excel's binary workbook), read with `pyxlsb`.
Anything else is refused, never guessed.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import py7zr

from traceconomics.archive.store import Archive
from traceconomics.checks import require

SOURCE = "elstat"
DATASET = re.compile(r"^puf-.*silc-(\d{4})$")
WORKBOOK = re.compile(r"Public Use Files\.xls[xb]$")
OUT_SOURCE = "oet-local"
OUT = "silc-tenure-gr-{year}"
GEO = "GR"
SMALL = 20  # counts under this are written as "<20", as in the HBS tables

TENURE = {"1": "owner", "2": "owner", "3": "renter_market", "4": "renter_reduced", "5": "rent_free"}  # HH021
TENURE_OLD = {"1": "owner", "2": "renter_market", "3": "renter_reduced", "4": "rent_free"}  # HH020
ROWS = ("all", "owner", "renter", "renter_market", "renter_reduced", "rent_free")
COLUMNS = [
    "geo",
    "ref_year",
    "tenure",
    "n_households",
    "households_weighted",
    "people_weighted",
    "rent_paid_eur",
    "source_version",
]
NEEDED = {"D_FILE": ("DB030", "DB090"), "H_FILE": ("HB030", "HH060"), "R_FILE": ("RB030", "RB040", "RB050")}


def years(archive: Archive) -> dict[int, str]:
    """{survey year: archive dataset} for every SILC public use file in the archive."""
    out = {}
    for source, dataset in archive.datasets():
        m = DATASET.match(dataset) if source == SOURCE else None
        if m:
            require(
                int(m.group(1)) not in out, f"two SILC files for {m.group(1)}: {out.get(int(m.group(1)))} and {dataset}"
            )
            out[int(m.group(1))] = dataset
    return dict(sorted(out.items()))


def read(archive: Archive, year: int) -> dict[str, pd.DataFrame]:
    """The D, H and R sheets of a year's file, as text, read from the archived 7z in memory."""
    dataset = years(archive).get(year)
    require(dataset is not None, f"no archived SILC public use file for {year}")
    rec = archive.latest(SOURCE, dataset)
    path = archive.root / rec["path"]
    require(path.suffix.lower() == ".7z", f"{path.name}: expected a .7z archive")
    with py7zr.SevenZipFile(path) as z:
        names = [n for n in z.getnames() if WORKBOOK.search(n)]
        require(len(names) == 1, f"{year}: expected one '... Public Use Files.xlsx' or '.xlsb', found {names}")
        factory = py7zr.io.BytesIOFactory(limit=500_000_000)
        z.extract(targets=names, factory=factory)
    buf = factory.products[names[0]]
    buf.seek(0)
    engine = "pyxlsb" if names[0].lower().endswith(".xlsb") else None
    book = pd.ExcelFile(io.BytesIO(buf.read()), engine=engine)
    sheets = {}
    for sheet, cols in NEEDED.items():
        # Written D_FILE from 2020, D-FILE before: the same sheet.
        names = [n for n in book.sheet_names if n.strip().upper().replace("-", "_") == sheet]
        require(
            len(names) == 1,
            f"{year}: expected one sheet {sheet} (or {sheet.replace('_', '-')}), found {book.sheet_names}",
        )
        sheets[sheet] = book.parse(names[0], dtype=str)
        missing = [c for c in cols if c not in sheets[sheet].columns]
        require(not missing, f"{year}: {sheet} has no {missing}")
    h = sheets["H_FILE"].columns
    require("HH021" in h or "HH020" in h, f"{year}: H_FILE has no tenure column (HH021 or HH020)")
    return sheets


def _number(s: pd.Series, what: str, blank_is_zero: bool = False) -> np.ndarray:
    text = s.fillna("").astype(str).str.strip()
    if blank_is_zero:
        text = text.replace("", "0")
    out = pd.to_numeric(text, errors="coerce")
    bad = text[out.isna()]
    require(bad.empty, f"{what}: values that aren't numbers, e.g. {bad.head(3).tolist()}")
    return out.to_numpy(float)


def _count(n: int) -> str:
    return "<20" if n < SMALL else str(n)


def table(sheets: dict[str, pd.DataFrame], year: int, source_version: str) -> pd.DataFrame:
    d, h, r = sheets["D_FILE"], sheets["H_FILE"], sheets["R_FILE"]
    hid = h.HB030.astype(str).str.strip()
    weights = pd.Series(_number(d.DB090, f"{year} DB090"), index=d.DB030.astype(str).str.strip())
    require(weights.index.is_unique, f"{year}: household ids repeat in D_FILE")
    require(hid.isin(weights.index).all(), f"{year}: households in H_FILE without a weight in D_FILE")
    w = weights.reindex(hid).to_numpy(float)
    column, mapping = ("HH021", TENURE) if "HH021" in h.columns else ("HH020", TENURE_OLD)
    codes = h[column].fillna("").astype(str).str.strip()
    unknown = sorted(set(codes) - set(mapping))
    require(not unknown, f"{year}: {column} codes not in ELSTAT's list: {unknown}")
    tenure = codes.map(mapping).to_numpy(object)
    rent = _number(h.HH060, f"{year} HH060", blank_is_zero=True)

    # People: each person's weight, summed by the tenure of their household.
    people = pd.Series(_number(r.RB050, f"{year} RB050"), index=r.RB040.astype(str).str.strip())
    require(people.index.isin(hid).all(), f"{year}: people in R_FILE whose household isn't in H_FILE")
    by_household = people.groupby(level=0).sum().reindex(hid).fillna(0).to_numpy(float)

    rows = []
    for label in ROWS:
        if label == "all":
            member = np.ones(len(w), bool)
        elif label == "renter":
            member = np.isin(tenure, ("renter_market", "renter_reduced"))
        else:
            member = tenure == label
        rows.append(
            {
                "geo": GEO,
                "ref_year": year,
                "tenure": label,
                "n_households": _count(int(member.sum())),
                "households_weighted": float(w[member].sum()),
                "people_weighted": float(by_household[member].sum()),
                # HH060 is monthly (see the module docstring): twelve months make the year.
                "rent_paid_eur": float(12 * (w * rent)[member].sum()),
                "source_version": source_version,
            }
        )
    return pd.DataFrame(rows)[COLUMNS]


def code_fingerprint() -> str:
    """This module's own hash: the provenance line names the code that built the table."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def run(archive: Archive, only: list[int] | None = None) -> list[dict]:
    """Build and archive each year's table (every archived SILC year unless `only`); one line of report each."""
    from traceconomics.local.weights import to_csv

    found = years(archive)
    report = []
    for year in only or list(found):
        rec = archive.latest(SOURCE, found.get(year, ""))
        require(rec is not None, f"no archived SILC public use file for {year}")
        source_version = f"{SOURCE}/{found[year]}@{rec['sha256'][:12]}"
        t = table(read(archive, year), year, source_version)
        head = [
            f"Greek EU-SILC {year}: tenure and rent paid for the main home, by household and person, euros a year.",
            "Built from the survey's public use file by Traceconomics; aggregates only. Counts under 20 are written as <20.",
            "provenance: "
            + json.dumps({"survey": source_version, "code_fingerprint": code_fingerprint()[:16]}, sort_keys=True),
        ]
        dataset = OUT.format(year=year)
        res = archive.store_bytes(
            OUT_SOURCE,
            dataset,
            to_csv(t, head),
            url=None,
            retrieved_at=datetime.now(UTC),
            ext=".csv",
            kind="local",
            extra={"original_name": f"{dataset}.csv", "note": "built locally"},
        )
        s = t.set_index("tenure")
        report.append(
            {
                "year": year,
                "result": res.status,
                "renters_households": round(
                    float(s.loc["renter", "households_weighted"] / s.loc["all", "households_weighted"]), 4
                ),
                "rent_paid_eur": int(round(float(s.loc["all", "rent_paid_eur"]))),
            }
        )
    return report
