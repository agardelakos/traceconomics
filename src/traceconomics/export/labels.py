"""Names of the spending categories (COICOP 2018 codes) in English and Greek, for the site.

Official wording only, never our own translation, from two sources in order:

1. EU Vocabularies, ECOICOP version 2 (the EU's COICOP 2018), in English and Greek: the EU's
   official translation, in normal case at every level. Its labels start with the dotted
   notation ("01.1.1.1 Cereals (ND)") and may end with a marker of the kind of product:
   (ND) non-durable, (SD) semi-durable, (D) durable, (S) service; in Greek (ΜΔΑ), (ΗΔΑ),
   (ΔΑ), (Υ). The notation and the marker are taken off the name; the marker is kept apart.
2. ELSTAT's household budget survey table 1.03 (COICOP 2018 from 2024), English and Greek
   files, for codes the first source lacks. ELSTAT writes higher levels in capitals, which in
   Greek drops the accents; such a name is replaced by its single child's name when the two
   are the same words (e.g. 01.3 and 01.3.0), and refused otherwise.

A code with no name from either source stops the export: a missing label is an error, not a
blank on the page. ELSTAT's CPI files aren't used: their names are all in capitals.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

from traceconomics.checks import require
from traceconomics.sources.elstat.hbs_tables import CODE, _rows, _text

MARKER = re.compile(r"\s*\((ND|SD|D|S|ΜΔΑ|ΗΔΑ|ΔΑ|Υ)\)\s*$")
NOTATION = re.compile(r"^\d{2}(\.\d)*\s+")
KIND = {"ND": "non-durable", "SD": "semi-durable", "D": "durable", "S": "service",
        "ΜΔΑ": "non-durable", "ΗΔΑ": "semi-durable", "ΔΑ": "durable", "Υ": "service"}


def clean(label: str) -> tuple[str, str | None]:
    """(name, kind) from a label: notation and marker taken off."""
    text = NOTATION.sub("", label.strip())
    m = MARKER.search(text)
    return (MARKER.sub("", text).strip(), KIND[m.group(1)] if m else None)


def _plain(text: str) -> str:
    """Upper case without accents or spaces: to compare a name in capitals with one that isn't."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if not unicodedata.combining(c) and not c.isspace()).upper()


def eu_vocabularies(path: Path) -> dict[str, dict]:
    out = {}
    with Path(path).open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            code = r["c"].rsplit("/", 1)[1]
            en, kind = clean(r["label_en"])
            el, _ = clean(r["label_el"])
            if en and el:
                out[code] = {"en": en, "el": el, "kind": kind, "source": "eu-vocabularies"}
    return out


def hbs_table(path: Path) -> dict[str, str]:
    """{code: label} from a table 1.03 in the 2024+ layout (code in column 3, name in column 4)."""
    out: dict[str, str] = {}
    for r in _rows(Path(path))[4:]:
        r = list(r) + [None] * 6
        code = _text(r[2])
        if CODE.match(code):
            out.setdefault(code, clean(_text(r[3]))[0])
    return out


def _uncapitalise(code: str, labels: dict[str, str]) -> str | None:
    name = labels[code]
    if name != name.upper():
        return name
    children = [c for c in labels if c.startswith(code) and len(c) == len(code) + 1]
    if len(children) == 1 and _plain(labels[children[0]]) == _plain(name):
        return _uncapitalise(children[0], labels)
    return None


def build(codes, eu_path: Path, hbs_en: Path, hbs_el: Path) -> dict[str, dict]:
    """{code: {en, el, kind, source}} for every code in `codes`; fails on any without a name."""
    eu = eu_vocabularies(eu_path)
    en, el = hbs_table(hbs_en), hbs_table(hbs_el)
    out, missing = {}, []
    for code in sorted(set(codes)):
        if code in eu:
            out[code] = eu[code]
            continue
        if code in en and code in el:
            e, g = _uncapitalise(code, en), _uncapitalise(code, el)
            if e and g:
                out[code] = {"en": e, "el": g, "kind": None, "source": "elstat-hbs"}
                continue
        missing.append(code)
    require(not missing, f"no English and Greek name for: {missing}")
    return out
