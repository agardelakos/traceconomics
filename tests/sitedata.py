"""Made-up data for the website, written by the real export code.

The site's browser tests need a full `site/public/data` folder, but the real one is built from
the archive and the household survey microdata, which never leave the owner's machines. This
module makes up prices and survey baskets in the shape the pipeline uses, runs them through the
real series code (`index.build` via `combinations.iterate`), the real output writer and the real
site export, and so writes files in exactly the format the site reads. Only the loading of
prices and weights from the store is skipped; the store's own files and the archive are real,
holding made-up rows and label files.

The numbers mean nothing. They are fixed (no randomness), so two runs write the same files, except
the generation time in `metadata.json`, as with real builds.

    python tests/sitedata.py <out>     # e.g. site/public/data (its made-up inputs go in a temporary folder)
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import openpyxl

from traceconomics.archive.store import Archive
from traceconomics.export import site
from traceconomics.module1 import availability, combinations, output
from traceconomics.module1.weights_used import CODED_2018_FROM, SUPPRESSED, Basket
from traceconomics.sources.elstat.parse import TOTAL

FIRST, LAST = 2008, 2026
LAST_MONTH = 9                            # the made-up data end in September of the last year
SURVEYS = range(2008, 2025)
PUBLISHED = datetime(2026, 10, 1)

# A small COICOP 2018 tree (compact codes, as the store holds them): division -> group -> leaves.
TREE = {
    "01": {"011": ["0111", "0114"], "012": ["0122"]},
    "02": {"021": ["0212"]},
    "03": {"031": ["0312"]},
    "04": {"041": ["0411"], "042": ["0421"], "045": ["0451"]},
    "05": {"051": ["0511"]},
    "06": {"061": ["0611"]},
    "07": {"072": ["0722"], "073": ["0732"]},
    "08": {"083": ["0830"]},
    "09": {"094": ["0941"]},
    "10": {"101": ["1010"], "102": ["1020"], "105": ["1050"]},
    "11": {"111": ["1111"]},
    "12": {"121": ["1211"]},
    "13": {"131": ["1311"]},
}
IMPUTED_RENT, TUTORING = "0421", "1050"   # no price index of their own: priced with 04.1.1 and 10.2.0
UNPRICED = {IMPUTED_RENT, TUTORING}
SMALL = "0114"                            # reported by too few households in the poorest groups
NAMES = {
    "01": ("Food and drinks", "Τρόφιμα και ποτά"), "02": ("Tobacco", "Καπνός"),
    "03": ("Clothing", "Ένδυση"), "04": ("Housing and energy", "Στέγαση και ενέργεια"),
    "05": ("Furnishings", "Επίπλωση"), "06": ("Health", "Υγεία"), "07": ("Transport", "Μεταφορές"),
    "08": ("Communication", "Επικοινωνία"), "09": ("Recreation", "Αναψυχή"), "10": ("Education", "Εκπαίδευση"),
    "11": ("Restaurants", "Εστιατόρια"),
    "12": ("Insurance and finance", "Ασφάλιση και χρηματοοικονομικά"), "13": ("Personal care", "Προσωπική φροντίδα"),
}


def codes() -> list[str]:
    out = []
    for div, groups in TREE.items():
        out.append(div)
        for grp, leaves in groups.items():
            out += [grp, *leaves]
    return out


def _seed(code: str) -> int:
    return int(hashlib.sha256(code.encode()).hexdigest()[:8], 16)


def level(code: str, year: int, month: int, *, hicp: bool = False) -> float:
    """A made-up price index: a steady trend per code, a seasonal wave, and a 2022 jump for energy."""
    t = (year - FIRST) * 12 + month
    trend = 0.004 + (_seed(code) % 9) * 0.0035 + (0.002 if hicp else 0.0)
    wave = 0.012 * math.sin(2 * math.pi * month / 12 + _seed(code) % 6)
    jump = 0.25 if code.startswith("045") and t >= (2022 - FIRST) * 12 else 0.0
    return round(100 * math.exp(trend * t / 12 + wave + jump), 3)


def blocks(*, hicp: bool = False) -> dict[int, dict]:
    """{year: {code: {"YYYY-MM": index}}}: each year's months and the December before it."""
    priced = [c for c in codes() if not c.startswith(tuple(u[:3] for u in UNPRICED))] + ([] if hicp else [TOTAL])
    out = {}
    for y in range(FIRST, LAST + 1):
        months = [(y - 1, 12)] + [(y, m) for m in range(1, (LAST_MONTH if y == LAST else 12) + 1)]
        out[y] = {c: {f"{yy}-{mm:02d}": level(c, yy, mm, hicp=hicp) for yy, mm in months} for c in priced}
    return out


def basket(survey: int, grouping: str, group: str, *, spending: str, imputed_rent: str) -> Basket:
    """Shares at every level; poorer groups spend more on food and housing, richer on transport."""
    rank = int(group[1]) - 1 if group[:1] == "Q" else {"renter": 1, "owner": 3, "pensioners": 1}.get(group, 2)
    tilt = (rank - 2) * 0.01 + {"A": 0.0, "B": 0.002, "C": -0.002}.get(grouping, 0.0) + (survey - 2016) * 0.0005
    leaf = {}
    for code in (c for c in codes() if len(c) == 4 and c not in UNPRICED):
        base = 0.05 + (_seed(code) % 5) * 0.012
        if code[:2] in ("01", "04"):
            base -= tilt
        elif code[:2] in ("07", "09", "11"):
            base += tilt
        leaf[code] = max(base + (0.004 if spending == "all" and code[:2] == "01" else 0.0), 0.01)
    if imputed_rent == "included" and group != "renter":
        leaf[IMPUTED_RENT] = 0.12
    if survey >= CODED_2018_FROM:
        # Coded in COICOP 2018: tutoring in 10.5, apart from the school levels.
        leaf[TUTORING] = 0.3 * (leaf["1010"] + leaf["1020"])
        leaf["1010"] *= 0.7
        leaf["1020"] *= 0.7
    total = sum(leaf.values())
    shares = {c: v / total for c, v in leaf.items()}
    for code in list(shares):
        for parent in (code[:3], code[:2]):
            shares[parent] = shares.get(parent, 0.0) + shares[code]
    tiers = dict.fromkeys(shares, "normal")
    if group == "Q1":
        tiers[SMALL] = SUPPRESSED
    return Basket(shares, tiers)


def baskets() -> dict[tuple[str, str], dict]:
    """{(spending, imputed rent): {(survey, grouping, group): Basket}}, as `combinations.iterate` takes them."""
    out = {}
    for spending in combinations.OPTIONS["spending"]:
        for imputed in combinations.OPTIONS["imputed_rent"]:
            out[(spending, imputed)] = {(h, g, q): basket(h, g, q, spending=spending, imputed_rent=imputed)
                                        for h in SURVEYS for g, q in combinations.GROUPS}
    return out


# The store: Parquet files in the store's layout, read through the real `open_views`.

COLUMNS = ["dataset", "archive_dataset", "key", "ref_period", "published_at", "published_at_quality",
           "retrieved_at", "value", "value_text", "status", "flags", "raw_sha256", "parser_version"]


def _write_dataset(store: Path, dataset: str, dims: list[str], rows) -> None:
    """rows: (archive_dataset, {dim: value}, ref_period, value)."""
    folder = store / "observations" / dataset.replace(":", ".")
    folder.mkdir(parents=True, exist_ok=True)
    text = io.StringIO()
    w = csv.writer(text, lineterminator="\n")
    w.writerow(COLUMNS[:3] + dims + COLUMNS[3:])
    sha = hashlib.sha256(dataset.encode()).hexdigest()
    for archive_dataset, d, period, value in rows:
        key = ",".join(f"{k}={d[k]}" for k in dims)
        w.writerow([dataset, archive_dataset, key, *(d[k] for k in dims), period, PUBLISHED.isoformat(sep=" "),
                    "first_seen", PUBLISHED.isoformat(sep=" "), value, repr(value), "final", None, sha, "1"])
    part = folder / "rows.csv"
    part.write_text(text.getvalue(), encoding="utf-8", newline="\n")
    types = {c: "VARCHAR" for c in COLUMNS[:3] + dims + COLUMNS[3:]}
    types.update(published_at="TIMESTAMP", retrieved_at="TIMESTAMP", value="DOUBLE")
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM read_csv('{part.as_posix()}', header = true, columns = {types!r})) "
                f"TO '{(folder / '00001-made-up.parquet').as_posix()}' (FORMAT parquet)")
    part.unlink()


def _cpi_rows(cpi):
    for y, block in cpi.items():
        for code, series in block.items():
            for period, v in series.items():
                yield f"elstat/doc-cpi07-{y}", {"freq": "M", "unit": "I20", "coicop18": code, "geo": "GR"}, period, v


def _published_rates(cpi):
    """ELSTAT's twelve-month rates as table 05 holds them (fractions), from the same made-up index."""
    total = {p: v for block in cpi.values() for p, v in block[TOTAL].items()}
    for period in sorted(total):
        y, m = period.split("-")
        before = total.get(f"{int(y) - 1}-{m}")
        if before:
            yield "elstat/doc-cpi05", {"freq": "M", "unit": "RCH_A_FR", "geo": "GR"}, period, total[period] / before - 1


BAND_DIMS = ["geo", "grouping", "group", "spending", "imputed_rent", "price_source", "weights_timing", "tutoring",
             "unit", "measure"]


def _band_rows():
    gaps = [(g, site.GAP) for g in combinations.GROUPINGS]
    months = [f"{y}-{m:02d}" for y in range(2010, LAST + 1) for m in range(1, 13) if (y, m) <= (LAST, LAST_MONTH)]
    for s in combinations.settings():
        for g, q in combinations.GROUPS + gaps:
            gap = q == site.GAP
            for unit, periods in ((("RCH_A_GAP", months), ("RCH_A_AVG_GAP", [str(y) for y in range(2010, LAST)]))
                                  if gap else (("RCH_A", months), ("RCH_A_AVG", [str(y) for y in range(2010, LAST)]))):
                d = {"geo": "GR", "grouping": g, "group": q, **s, "unit": unit, "measure": "se"}
                for n, p in enumerate(periods):
                    yield "oet-local/hbs-bands-gr", d, p, round(0.08 + 0.04 * math.sin(n / 9) ** 2 + (0.05 if gap else 0), 4)


def write_store(store: Path, cpi, hicp) -> None:
    _write_dataset(store, "elstat:cpi07", ["freq", "unit", "coicop18", "geo"],
                   (r for r in _cpi_rows(cpi) if int(r[0][-4:]) >= 2011))   # table 07 from 2011, as ELSTAT re-issued it
    _write_dataset(store, "elstat:cpi05", ["freq", "unit", "geo"], _published_rates(cpi))
    _write_dataset(store, "eurostat:prc_hicp_minr", ["freq", "unit", "coicop18", "geo"],
                   (("eurostat/prc_hicp_minr", {"freq": "M", "unit": "I25", "coicop18": c, "geo": "GR"}, p, v)
                    for block in hicp.values() for c, series in block.items() for p, v in series.items()))
    _write_dataset(store, "oet-local:hbs_weights", ["geo", "grouping", "group", "coicop18", "measure"],
                   (("oet-local/hbs-weights-gr", {"geo": "GR", "grouping": "all", "group": "all", "coicop18": c,
                                                  "measure": "share"}, str(h), v)
                    for h in SURVEYS for c, v in basket(h, "all", "all", spending="purchases",
                                                         imputed_rent="excluded").shares.items()))
    _write_dataset(store, "oet-local:hbs_bands", BAND_DIMS, _band_rows())


# The archive: the label files the export reads, made up in their publishers' formats.

def _labels_csv() -> bytes:
    text = io.StringIO()
    w = csv.writer(text, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(["c", "notation", "label_en", "label_el"])
    for code in codes():
        en, el = NAMES[code[:2]]
        if len(code) > 2:
            en, el = f"{en}, item {code}", f"{el}, είδος {code}"
        notation = code[:2] + "".join(f".{d}" for d in code[2:])
        # Only items carry a marker of the kind of product, as in the real file.
        kind = (" (S)", " (Υ)") if len(code) == 4 else ("", "")
        w.writerow([f"http://data.europa.eu/ed1/ecoicop2/{code}", notation, f"{notation} {en}{kind[0]}", f"{notation} {el}{kind[1]}"])
    return text.getvalue().encode("utf-8")


def _table_103(lang: str) -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    for _ in range(4):
        sheet.append(["Made-up table 1.03"])
    sheet.append([None, None, "01", NAMES["01"][0 if lang == "EN" else 1].upper()])
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


def write_archive(root: Path) -> Archive:
    archive = Archive(root)
    when = PUBLISHED.replace(tzinfo=UTC)
    archive.store_bytes("eu-vocabularies", "ecoicop2-labels", _labels_csv(), url=None, retrieved_at=when, ext=".csv")
    for n, lang in enumerate(("EN", "GR")):
        archive.store_bytes("elstat", f"doc-10{n}", _table_103(lang), url=None, retrieved_at=when, ext=".xlsx",
                            extra={"original_name": f"SFA05_TB_AN_00_2024_103_F_{lang}.xlsx"})
    return archive


def module1_outputs(outputs: Path, store_con, cpi, hicp, kept) -> None:
    """What `traceconomics module1 run --combinations all` writes, from the made-up inputs."""
    folder = outputs / "gr" / "m1"
    writer, summaries = output.Writer(folder), []
    for _, series, used in combinations.iterate(None, None, blocks={"cpi": cpi, "hicp": hicp}, baskets=kept):
        writer.add(series, used)
        summaries += [availability.Summary.of(s) for s in series]
    writer.close()
    availability.write(folder, availability.build(summaries))
    output.write_metadata(folder, first_period=writer.first_period, last_period=writer.last_period,
                          manifest=output.manifest(store_con))


def generate(out: Path, work: Path, *, log=print) -> list[Path]:
    """Write the made-up site data into `out` (e.g. site/public/data); `work` holds the store,
    the archive and module 1's outputs."""
    from traceconomics.store.query import open_views

    cpi, hicp, kept = blocks(), blocks(hicp=True), baskets()
    write_store(work / "store", cpi, hicp)
    archive = write_archive(work / "archive")
    con = duckdb.connect()
    open_views(con, work / "store")
    module1_outputs(work / "outputs", con, cpi, hicp, kept)
    return site.export(con, archive, work / "outputs", out, log=log,
                       blocks={"cpi": cpi, "hicp": hicp}, baskets=kept)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    target = Path(sys.argv[1])
    # Not next to the target: everything under site/public is published with the site.
    with tempfile.TemporaryDirectory() as scratch:
        files = generate(target, Path(scratch))
    print(f"Wrote {len(files)} files to {target}")
