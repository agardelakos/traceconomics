"""Read one year of ELSTAT's household budget survey public use file (PUF), from the archived download.

The archive holds the file exactly as downloaded: a .7z (2008-2019) or .zip
(2020 on) with a household file, a person file and two codebooks. It is
read in memory; nothing is unpacked to disk, and names inside the archive
(some in Greek) are only matched, never used as paths.

The files differ by era, and this module hides that:

- separator: ";" except the 2023 "ver2" files, which use "," (with decimal commas in
  quoted values)
- spending: one column per COICOP code and mode: A purchases, B non-monetary,
  and the all-modes total, which is `C` in 2008-2016 and 2024 and has no
  suffix in 2017-2023. Annual euros; a blank means nothing spent.
- codes: a national 5-digit list in 2008-2014, ECOICOP version 1 subclasses in 2015-2023 (both
  COICOP 1999 based), COICOP 2018 from 2024.
  A few codes have no all-modes column; there it is purchases plus
  non-monetary, which is what the column holds wherever it exists (checked).
- household identity: `HA04`, except 2023, where `HA04` is the household's
  number within its cluster (`HA07`). The person file links to households in
  one of several ways (`PERSON_LINKS`); the one that links every person is
  used, and the read fails if none does.
- strata `HA06` and clusters `HA07` are absent in some years (see `design`).
- 2008: six households (one cluster) have no person records; they are kept
  and listed in `households_without_persons`.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import py7zr

from traceconomics.archive.store import Archive
from traceconomics.checks import FormatError, require

SOURCE = "elstat"
HOUSEHOLD_FILE = re.compile(r"^hbs_h[hs]_basic_\d{4}.*\.csv$", re.IGNORECASE)
PERSON_FILE = re.compile(r"^hbs_hm_basic_\d{4}.*\.csv$", re.IGNORECASE)
SPEND = re.compile(r"^HE(\d{2,6})([ABC]?)$")


def dataset(year: int) -> str:
    return f"puf-hbs-{year}"


def classification(year: int) -> str:
    """The survey's code list: the national list of 2008-2014 ("hbs-gr-2008"), ECOICOP version 1
    subclasses (2015-2023) or COICOP 2018 (from 2024)."""
    return "coicop2018" if year >= 2024 else "ecoicop1" if year >= 2015 else "hbs-gr-2008"


@dataclass
class Survey:
    year: int
    classification: str            # see `classification`
    households: pd.DataFrame       # one row per household, see `read`
    persons: pd.DataFrame          # hh, age
    spending: pd.DataFrame         # all modes, annual euros; columns are codes, index aligned with households
    purchases: pd.DataFrame        # mode A only (what the published table 1.03 shows)
    design: str                    # "full", "no-strata" or "no-clusters"
    source_sha256: str
    person_link: str = ""
    households_without_persons: tuple[str, ...] = ()
    derived_totals: tuple[str, ...] = ()   # codes whose all-modes total is purchases + non-monetary


def _members(path: Path) -> dict[str, bytes]:
    """{file name without folders: bytes} for the two CSV files."""
    wanted: dict[str, bytes] = {}
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                base = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
                if HOUSEHOLD_FILE.match(base) or PERSON_FILE.match(base):
                    wanted[base] = z.read(info)
    elif path.suffix.lower() == ".7z":
        with py7zr.SevenZipFile(path) as z:
            names = [i.filename for i in z.list() if not i.is_directory]
            keep = [n for n in names if HOUSEHOLD_FILE.match(n.rsplit("/", 1)[-1]) or PERSON_FILE.match(n.rsplit("/", 1)[-1])]
            factory = py7zr.io.BytesIOFactory(limit=500_000_000)
            z.extract(targets=keep, factory=factory)
            for n in keep:
                buf = factory.products[n]
                buf.seek(0)
                wanted[n.rsplit("/", 1)[-1]] = buf.read()
    else:
        raise FormatError(f"{path.name}: not a .zip or .7z archive")
    return wanted


def _table(data: bytes, name: str) -> pd.DataFrame:
    text = data.decode("latin-1")
    head = text.split("\n", 1)[0]
    sep = ";" if head.count(";") > head.count(",") else ","
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    # Decimals are written with a comma in every era; in the "," files of 2023 such values are
    # quoted, so once the file is parsed any comma left in a value is a decimal comma.
    df = df.apply(lambda s: s.str.replace(",", ".", regex=False))
    require(len(df) > 100, f"{name}: only {len(df)} rows")
    return df


def _number(s: pd.Series, what: str) -> pd.Series:
    out = pd.to_numeric(s.str.strip().replace("", "0"), errors="coerce")
    bad = s[out.isna()]
    require(bad.empty, f"{what}: values that aren't numbers, e.g. {bad.head(3).tolist()}")
    return out


# Ways the person file points at its household, tried in order.
PERSON_LINKS = {
    "MA04 is the household": lambda pp: pp["MA04"],
    "MA04 = household + person number": lambda pp: pp["MA04"].str[:-2],
    "cluster + 2 digits of MA04": lambda pp: pp["HA07"] + pp["MA04"].str[-4:-2],
    "cluster - household number in MA04": lambda pp: pp["HA07"] + "-" + pp["MA04"].str[:2].str.lstrip("0"),
}


def _spending(hh: pd.DataFrame, year: int) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    by_code: dict[str, set[str]] = {}
    for col in hh.columns:
        if m := SPEND.match(col):
            by_code.setdefault(m.group(1), set()).add(m.group(2))
    require(by_code, f"{year}: no spending columns")
    all_modes, purchases, derived = {}, {}, []
    for code, suffixes in sorted(by_code.items()):
        a = _number(hh[f"HE{code}A"], f"{year} HE{code}A") if "A" in suffixes else None
        b = _number(hh[f"HE{code}B"], f"{year} HE{code}B") if "B" in suffixes else None
        total_col = f"HE{code}C" if "C" in suffixes else f"HE{code}" if "" in suffixes else None
        if total_col is not None:
            total = _number(hh[total_col], f"{year} {total_col}")
            if a is not None and b is not None:
                gap = (total - a - b).abs().max()
                require(gap < 0.011, f"{year}: {total_col} isn't purchases + non-monetary (off by up to {gap:.2f})")
        else:
            require(a is not None and b is not None, f"{year}: code {code} has only {sorted(suffixes)}")
            total = a + b
            derived.append(code)
        all_modes[code] = total
        if a is not None:
            purchases[code] = a
    return pd.DataFrame(all_modes), pd.DataFrame(purchases), tuple(derived)


def read(archive: Archive, year: int) -> Survey:
    rec = archive.latest(SOURCE, dataset(year))
    require(rec is not None, f"no archived PUF for {year} ({SOURCE}/{dataset(year)}); add it with `traceconomics import`")
    path = archive.root / rec["path"]
    files = _members(path)
    hh_names = [n for n in files if HOUSEHOLD_FILE.match(n)]
    p_names = [n for n in files if PERSON_FILE.match(n)]
    require(len(hh_names) == 1 and len(p_names) == 1,
            f"{year}: expected one household and one person file, found {sorted(files)}")
    hh = _table(files[hh_names[0]], hh_names[0])
    pp = _table(files[p_names[0]], p_names[0])

    for col in ("HA04", "HA08", "HA10", "HH095", "HH099", "HI11"):
        require(col in hh.columns, f"{year}: household file has no {col}")
    require("MB03" in pp.columns and "MA04" in pp.columns, f"{year}: person file has no MA04/MB03")

    # Household identity and the person link (see the module docstring).
    hh_id = hh["HA07"] + "-" + hh["HA04"].str.lstrip("0") if year == 2023 else hh["HA04"]
    require(hh_id.is_unique, f"{year}: household identifiers are not unique")
    ids = set(hh_id)
    link_name, p_id = None, None
    for name, rule in PERSON_LINKS.items():
        try:
            candidate = rule(pp)
        except KeyError:
            continue
        if candidate.isin(ids).all():
            link_name, p_id = name, candidate
            break
    require(p_id is not None, f"{year}: no person-link rule links every person to a household")
    people = pd.DataFrame({"hh": p_id, "age": _number(pp["MB03"], f"{year} MB03")})
    without = tuple(sorted(ids - set(people.hh)))
    require(len(without) <= 10, f"{year}: {len(without)} households have no person records")

    design = "full"
    if "HA07" not in hh.columns:
        design = "no-clusters"
    elif "HA06" not in hh.columns:
        design = "no-strata"
    households = pd.DataFrame({
        "hh": hh_id,
        "weight": _number(hh["HA10"], f"{year} HA10"),
        "region": hh["HA08"],
        "stratum": hh["HA06"] if "HA06" in hh.columns else None,
        "cluster": hh["HA07"] if "HA07" in hh.columns else None,
        # Money income after taxes (HH095) is what households are ranked by; the total (HH099)
        # adds income in kind and imputed rent.
        "money_income": _number(hh["HH095"], f"{year} HH095"),
        "total_income": _number(hh["HH099"], f"{year} HH099"),
        "main_income_source": hh["HI11"].str.strip(),
    })
    require((households.weight > 0).all(), f"{year}: households with no weight")
    spending, purchases, derived = _spending(hh, year)
    return Survey(
        year=year,
        classification=classification(year),
        households=households.reset_index(drop=True),
        persons=people.reset_index(drop=True),
        spending=spending.reset_index(drop=True),
        purchases=purchases.reset_index(drop=True),
        design=design,
        source_sha256=rec["sha256"],
        person_link=link_name,
        households_without_persons=without,
        derived_totals=derived,
    )
