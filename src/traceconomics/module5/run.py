"""Run every check and write the results: `<out>/<country>/m5/`.

    checks.json        every check's summary: what was compared, how often the sides agree,
                       and each difference with its explanation
    <check id>.csv     every period compared, agreeing or not (the download)
    <question id>.csv  "Same question, different sources": every source's value by period

A check or question whose inputs aren't in the store yet (e.g. the survey tables before the
first `weights run`) is left out, and the run says so.

Both are rebuilt from the store on every run, byte-identical wherever they are built: rows in
period order, floats written as Python writes them, text files with "\n".
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from traceconomics.checks import require
from traceconomics.module5 import cpi, hbs, questions, rebuilds
from traceconomics.module5.record import Check, load_explanations

FORMAT = "m5-v1"
LICENCE = "CC BY 4.0"
# The publishers' reuse terms ask for the source, a clear statement that the data were modified,
# and that they bear no responsibility for the result (SOURCES.md).
ATTRIBUTION = (
    "Computed by TracEconomics from data of the Hellenic Statistical Authority (ELSTAT, www.statistics.gr), "
    "Eurostat, the Independent Authority for Public Revenue (AADE, www.aade.gr) and the European Commission "
    "(DG EMPL, labour market policy database, data from the national public employment services): "
    "ELSTAT's Consumer Price Index (tables 05 and 07), Household Budget Survey and EU-SILC public use files; "
    "Eurostat's HICP item indices and weights (prc_hicp_minr, doi:10.2908/PRC_HICP_MINR; prc_hicp_iw), EU-SILC tables (ilc_di01, ilc_lvho02), "
    "national accounts (nama_10_co3_p3, nasa_10_nf_tr), labour force survey (une_rt_a) "
    "and censuses (cens_11htts_r2, cens_21hhct_r3); AADE's statistics of personal income tax returns; the "
    "LMP database's registered unemployed (lmp_rjru). AADE's figures are shown as published, never modified "
    "(its terms forbid it). The other data have been modified: these comparisons are our own calculations, "
    "not official statistics. ELSTAT, Eurostat and the European Commission bear no responsibility for the "
    "result of the modification."
)
COLUMNS = ["period", "published", "rebuilt", "difference", "agree", "explanation", "finding"]


def all_checks(store_con, archive, archive_dir: Path, duck) -> list[Check]:
    """Every check. `duck`: a spare DuckDB connection the HICP rebuild parses Eurostat's files into."""
    explanations = load_explanations()
    found = cpi.checks(store_con, explanations)
    found.append(rebuilds.cpi(archive, explanations))
    hicp = rebuilds.hicp(archive, Path(archive_dir), duck, explanations)
    if hicp is not None:
        found.append(hicp)
    types = hbs.load_types(store_con)
    if types:
        found.append(hbs.household_types(types, explanations))
    spending = hbs.load_spending(store_con)
    if spending:
        found.append(hbs.spending(spending))
    ids = [c.id for c in found]
    # A real check, not an assert: `python -O` drops asserts, and two checks with one id would
    # overwrite each other's files.
    require(len(ids) == len(set(ids)), f"check ids repeat: {ids}")
    return found


def all_questions(store_con) -> list[hbs.Question]:
    ours, silc = hbs.load_limits(store_con)
    found = [hbs.income_limits(ours, silc)] if ours and silc else []
    return found + questions.all_questions(store_con)


def write(checks: list[Check], out: Path, questions: list[hbs.Question] = ()) -> list[Path]:
    written = []
    for country in sorted({c.country for c in [*checks, *questions]}):
        folder = Path(out) / country / "m5"
        folder.mkdir(parents=True, exist_ok=True)
        mine = sorted((c for c in checks if c.country == country), key=lambda c: c.id)
        for c in mine:
            path = folder / f"{c.id}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(COLUMNS)
                for x in sorted(c.comparisons, key=lambda x: x.period):
                    w.writerow(
                        [
                            x.period,
                            repr(x.published),
                            repr(x.rebuilt),
                            repr(x.difference),
                            "yes" if x.agree else "no",
                            x.explanation,
                            x.finding,
                        ]
                    )
            written.append(path)
        asked = sorted((q for q in questions if q.country == country), key=lambda q: q.id)
        for q in asked:
            path = folder / f"{q.id}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(["period", "source", "value"])
                for label in sorted(q.values):
                    for period in sorted(q.values[label]):
                        w.writerow([period, label, repr(q.values[label][period])])
            written.append(path)
        path = folder / "checks.json"
        doc = {
            "format": FORMAT,
            "country": country,
            "licence": LICENCE,
            "attribution": ATTRIBUTION,
            "checks": [c.summary() for c in mine],
            "questions": [q.summary() for q in asked],
        }
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        written.append(path)
    return written
