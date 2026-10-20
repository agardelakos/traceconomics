"""Write module 1's results: one folder, rebuildable from the store at any time.

    <out>/gr/m1/m1_index.{csv,parquet}          the group indices (2025 = 100)
    <out>/gr/m1/m1_rates.{csv,parquet}          annual, monthly and annual-average rates; the Q1-Q5 gap
    <out>/gr/m1/m1_weights_used.{csv,parquet}   the price-updated weights each index year used
    <out>/gr/m1/m1_contributions.{csv,parquet}  each division's contribution to each group's annual
                                                rate, and to the Q1-Q5 gap (percentage points)
    <out>/gr/m1/availability.{json,csv}         which periods each option covers, what is greyed
                                                out and why, and per-combination notes
    <out>/gr/m1/metadata.json                   dimensions, sources, method notes, and a manifest
                                                of every input the numbers came from
    <out>/gr/m1/validation/...                  groups computed only to check other studies' settings

The Parquet files hold every combination of the options; the CSV files hold the default
combination only (all of them as CSV would be about 1.5 GB).

Series are keyed by named dimensions in a fixed order (`KEY`): adding an option later adds a
value, never a new identity. The files hold no run date in their rows; the manifest records when
they were built and from which input files.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

import duckdb

from traceconomics import __version__, references
from traceconomics.module1.index import DEFAULT_OPTIONS, Series

KEY = ["geo", "grouping", "group", "spending", "imputed_rent", "price_source", "weights_timing", "tutoring",
       "hh_weighting", "coicop18", "unit"]
DEFAULTS = {"geo": "GR", **DEFAULT_OPTIONS, "hh_weighting": "plutocratic"}
SOURCES = ["hicp-manual-2024", "reg-2020-1148", "reg-2016-792", "cpi-manual-2020", "elstat-cpi-qr-2026",
           "elstat-cpi-sims-2026", "eurostat-equivalence-scale", "reg-1982-2003", "preston-2009"]
CODE = {"traceconomics.module1": ("schedule.py", "prices.py", "weights_used.py", "index.py", "output.py", "contributions.py",
                        "combinations.py", "originals.py"),
        "traceconomics.engine": ("chain.py", "tree.py", "rates.py")}
GAP = ("Q1", "Q5")


def code_fingerprint() -> str:
    # Line endings are normalised: a Windows checkout (CRLF) and a Linux one (LF) of the same code
    # must give the same fingerprint.
    h = hashlib.sha256()
    for package, names in CODE.items():
        for name in names:
            h.update(resources.files(package).joinpath(name).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


LESS_CERTAIN = "less certain"
COARSER = "coarser detail"
# The last index year each flag covers, by price source:
#  - CPI: 2009-2010 rest on ELSTAT's original price tables, an older version of the prices than
#    the re-issued series used from 2011;
#  - HICP: Eurostat's Greek item indices reach the finest (5-digit) level only from 2015, so
#    before that items are priced with their class or group, which hides differences between
#    households that buy different things within it.
FLAGS = {"cpi": (LESS_CERTAIN, 2010), "hicp": (COARSER, 2014)}


def quality(unit: str, period: str, price_source: str = "cpi") -> str:
    """The flag for a value: on the index months up to December of the flag's last year, and on
    every value that compares with them (annual rates and contributions to the next December,
    monthly rates to the next January, annual averages to the next year)."""
    flag, year = FLAGS[price_source]
    if unit.startswith("I"):
        last = f"{year}-12"
    elif unit == "SHARE":
        last = str(year)
    elif unit == "RCH_M":
        last = f"{year + 1}-01"
    elif unit in ("RCH_A_AVG", "RCH_A_AVG_GAP"):
        last = str(year + 1)
    else:
        last = f"{year + 1}-12"
    return flag if period <= last else ""


TABLES = ("m1_index", "m1_rates", "m1_weights_used", "m1_contributions")
VALUE_COLS = ["ref_period", "value", "value_text", "status", "quality", "weights_status"]
COLUMNS = {name: KEY + VALUE_COLS + (["survey", "priced_with"] if name == "m1_weights_used" else [])
           for name in TABLES}
REST = "_REST"     # suffix of a "rest of" row: a parent's small cells, together
LOW_RELIABILITY = "low reliability"


def is_default_row(r: dict) -> bool:
    return r["spending"] == "purchases" and all(r[k] == v for k, v in DEFAULTS.items())


def _key(s: Series, unit: str, group: str | None = None, code: str = "TOTAL") -> dict:
    return {**DEFAULTS, **s.options, "grouping": s.grouping, "group": group or s.group, "spending": s.spending,
            "coicop18": code, "unit": unit}


def published_weights(u) -> dict[str, tuple[float, str, int]]:
    """{code: (weight, priced with, cells)}: cells with fewer than 20 reporting households are
    merged into one "rest of" row per parent, so no small cell is shown on its own (the
    computation prices them at that parent's level too). A rest row that holds a single cell
    still describes that cell, so it is flagged "low reliability"."""
    out: dict[str, tuple[float, set, int]] = {}
    for code, w in u.weights.items():
        target = f"{u.small[code]}{REST}" if code in u.small else code
        total, priced, n = out.get(target, (0.0, set(), 0))
        out[target] = (total + w, priced | {u.price_with.get(code, code)}, n + 1)
    return {c: (w, "+".join(sorted(p)), n) for c, (w, p, n) in out.items()}


def series_rows(s: Series, contrib=None):
    """(table, row) for one series."""
    src = s.options["price_source"]
    status = {e.year: e.status for e in s.schedule}

    def row(unit, period, value, text, code="TOTAL", wstatus=None):
        return {**_key(s, unit, code=code), "ref_period": period, "value": value, "value_text": text,
                "status": "backcast", "quality": quality(unit, period, src),
                "weights_status": status.get(int(period[:4]), "") if wstatus is None else wstatus}

    for period, v in sorted(s.published.items()):
        yield "m1_index", row(s.index_unit, period, v, f"{v:.2f}")
    for period, r in s.rates().items():
        for name, unit in (("annual", "RCH_A"), ("monthly", "RCH_M")):
            if name in r:
                yield "m1_rates", row(unit, period, r[name], f"{r[name]:.1f}")
    for year, r in s.annual_average_rates().items():
        yield "m1_rates", row("RCH_A_AVG", str(year), r, f"{r:.1f}")
    for year, u in sorted(s.used.items()):
        for code, (w, priced, cells) in sorted(published_weights(u).items()):
            r = row("SHARE", str(year), w, f"{w:.10g}", code=code, wstatus=u.entry.status)
            if code.endswith(REST) and cells == 1:
                r["quality"] = "; ".join(q for q in (r["quality"], LOW_RELIABILITY) if q)
            yield "m1_weights_used", {**r, "survey": u.entry.survey, "priced_with": priced}
    for period, parts in sorted((contrib or {}).items()):
        for h, v in sorted(parts.items()):
            yield "m1_contributions", row("PC_PNT", period, v, f"{v:.2f}", code=h)


def gap_rows(lo: Series, hi: Series, clo=None, chi=None):
    """(table, row) for the Q1-Q5 gap of one grouping and setting."""
    src = lo.options["price_source"]
    gap_group = f"{GAP[0]}-{GAP[1]}"

    def row(unit, period, value, text, code="TOTAL"):
        return {**_key(lo, unit, gap_group, code), "ref_period": period, "value": value, "value_text": text,
                "status": "backcast", "quality": quality(unit, period, src), "weights_status": ""}

    a, b = lo.rates(), hi.rates()
    for period in sorted(set(a) & set(b)):
        if "annual" in a[period] and "annual" in b[period]:
            # The gap is shown as the difference of the two rates as shown (one decimal each).
            g = round(a[period]["annual"], 1) - round(b[period]["annual"], 1)
            yield "m1_rates", row("RCH_A_GAP", period, g, f"{g:.1f}")
    if clo and chi:
        for period in sorted(set(clo) & set(chi)):
            for h in sorted(set(clo[period]) | set(chi[period])):
                g = clo[period].get(h, 0.0) - chi[period].get(h, 0.0)
                yield "m1_contributions", row("PC_PNT_GAP", period, g, f"{g:.2f}", code=h)
    aa, bb = lo.annual_average_rates(), hi.annual_average_rates()
    for year in sorted(set(aa) & set(bb)):
        g = round(aa[year], 1) - round(bb[year], 1)
        yield "m1_rates", row("RCH_A_AVG_GAP", str(year), g, f"{g:.1f}")


def setting_of(s: Series) -> tuple:
    return (s.spending, *sorted(s.options.items()))


def iter_rows(series: list[Series], blocks=None):
    """(table, row) for a list of series, then the Q1-Q5 gap of every quintile grouping and
    setting. `blocks`: {price source: blocks}, or one source's blocks for all; without them, no
    contributions."""
    contrib = {}
    if blocks is not None:
        from traceconomics.module1.contributions import ribe
        by_source = set(blocks) <= set(FLAGS)
        for s in series:
            contrib[id(s)] = ribe(s, blocks[s.options["price_source"]] if by_source else blocks)
    for s in series:
        yield from series_rows(s, contrib.get(id(s)))
    by = {(s.grouping, s.group, setting_of(s)): s for s in series}
    for (grouping, group, setting), lo in by.items():
        hi = by.get((grouping, GAP[1], setting))
        if group == GAP[0] and hi is not None:
            yield from gap_rows(lo, hi, contrib.get(id(lo)), contrib.get(id(hi)))


def rows(series: list[Series], blocks=None) -> dict[str, list[dict]]:
    out = {name: [] for name in TABLES}
    for name, r in iter_rows(series, blocks):
        out[name].append(r)
    return out


class Writer:
    """Streams rows to disk a batch of series at a time: every combination into Parquet, the
    default combination also into CSV."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._files, self._writers, self.counts = {}, {}, {name: 0 for name in TABLES}
        for name in TABLES:
            for kind, path in (("all", self.folder / f"{name}.all.csv.part"), ("default", self.folder / f"{name}.csv")):
                f = path.open("w", newline="", encoding="utf-8")
                w = csv.DictWriter(f, fieldnames=COLUMNS[name], lineterminator="\n")
                w.writeheader()
                self._files[(name, kind)], self._writers[(name, kind)] = f, w
        self.first_period = self.last_period = None

    def add(self, series: list[Series], blocks=None) -> None:
        for s in series:
            if s.published:
                lo, hi = min(s.published), max(s.published)
                self.first_period = min(self.first_period or lo, lo)
                self.last_period = max(self.last_period or hi, hi)
        for name, r in iter_rows(series, blocks):
            self._writers[(name, "all")].writerow(r)
            self.counts[name] += 1
            if is_default_row(r):
                self._writers[(name, "default")].writerow(r)

    def close(self) -> list[Path]:
        for f in self._files.values():
            f.close()
        written = []
        con = duckdb.connect()
        for name in TABLES:
            part = self.folder / f"{name}.all.csv.part"
            parquet = self.folder / f"{name}.parquet"
            con.execute(f"COPY (SELECT * FROM read_csv('{part.as_posix()}', header = true, all_varchar = true)) "
                        f"TO '{parquet.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
            part.unlink()
            written += [self.folder / f"{name}.csv", parquet]
        return written


def _write(folder: Path, name: str, table: list[dict]) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    csv_path = folder / f"{name}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS[name], lineterminator="\n")
        w.writeheader()
        w.writerows(table)
    parquet = folder / f"{name}.parquet"
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM read_csv('{csv_path.as_posix()}', header = true, all_varchar = true)) "
                f"TO '{parquet.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    return [csv_path, parquet]


def write_validation(folder: Path, validation: list[Series], blocks=None) -> list[Path]:
    written = []
    for name, table in rows(validation, blocks).items():
        if table:
            written += _write(Path(folder) / "validation", name, table)
    return written


UNITS = {"I25": "index, 2025 = 100", "I24": "index, 2024 = 100 (a series that ends before 2025)",
         "RCH_A": "percent change on the same month a year earlier",
         "RCH_M": "percent change on the previous month", "RCH_A_AVG": "percent change in the annual average",
         "RCH_A_GAP": "Q1's annual rate minus Q5's, percentage points (rates as shown)",
         "RCH_A_AVG_GAP": "the same for annual averages",
         "SHARE": f"weight used, share of 1; a code ending {REST} holds a parent's cells with fewer than 20 "
                  "reporting households, together",
         "PC_PNT": "contribution to the annual rate, percentage points (Ribe, HICP Manual 2024 eq. 8.42)",
         "PC_PNT_GAP": "contribution to the Q1-Q5 gap: Q1's contribution minus Q5's"}

NOTES = [
    "Every combination of the options is in the Parquet files; availability.json says which periods each covers, "
    "what is greyed out and why.",
    "CPI prices for 2009-2010 come from ELSTAT's original CPI tables (from the Wayback Machine's copy of its old "
    "site): the re-issued series in today's classification start in 2010-01. They are an older version of the "
    "prices and are flagged 'less certain'; within 2010 the two versions differ by 0.06-0.10 pp for every group.",
    "Footnote: the 2008-2014 household surveys' public files leave out hospital services; availability.json lists "
    "the periods each combination's rates rest on them.",
    "Everything here was computed after the fact (status backcast).",
]


def write_metadata(folder: Path, *, first_period, last_period, manifest: dict, notes=NOTES) -> Path:
    missing = references.missing(SOURCES)
    if missing:
        raise ValueError(f"sources not in the bibliography: {missing}")
    meta = {
        "title": "Greece: consumer price inflation by household group",
        "key": KEY,
        "defaults": DEFAULTS,
        "units": UNITS,
        "quality": {LESS_CERTAIN: "CPI prices: rests on ELSTAT's original 2008-2010 price tables, an older version "
                                  "of the prices than the re-issued series used from 2011",
                    COARSER: "HICP prices: before 2015 Eurostat's Greek item indices exist only for classes and "
                             "groups, so the items within one share its price movement"},
        "files": {"csv": "the default combination only", "parquet": "every combination"},
        "first_period": first_period,
        "last_period": last_period,
        "notes": notes,
        "sources": SOURCES,
        "code_version": __version__, "code_fingerprint": code_fingerprint(),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "manifest": manifest,
        "licence": "CC BY 4.0",
        "attribution": ("Prices: ELSTAT, Consumer Price Index (table 07), and Eurostat, HICP item indices "
                        "(prc_hicp_minr). Weights: computed by Traceconomics from ELSTAT's Household Budget "
                        "Survey public use files. ELSTAT and Eurostat bear no responsibility for these figures."),
    }
    path = Path(folder) / "metadata.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def write(out_dir: Path, series: list[Series], validation: list[Series], manifest: dict, blocks=None) -> list[Path]:
    """Write a list of series in one go (a few series, or tests)."""
    folder = Path(out_dir) / "gr" / "m1"
    w = Writer(folder)
    w.add(series, blocks)
    written = w.close() + write_validation(folder, validation, blocks)
    written.append(write_metadata(folder, first_period=w.first_period, last_period=w.last_period, manifest=manifest))
    return written


def manifest(con) -> dict:
    """Which archived files the inputs came from, and how fresh they were."""
    out = {}
    for dataset in ("elstat:cpi07", "eurostat:prc_hicp_minr", "oet-local:hbs_weights"):
        shas = con.execute("SELECT DISTINCT raw_sha256 FROM observations WHERE dataset = ? ORDER BY 1", [dataset]).fetchall()
        newest = con.execute("SELECT max(published_at) FROM observations WHERE dataset = ?", [dataset]).fetchone()[0]
        out[dataset] = {"files": [s[0] for s in shas], "newest_published_at": str(newest)}
    return out
