"""Read the weights tables that the local survey run writes (source `oet-local`) into the store.

The archived files are wide CSV tables, opened by `#` lines (their provenance). In the store each
value is its own row, keyed by the table's dimensions plus a `measure` column: `share`, `se`,
`n_households_unweighted`, `reliability` for the weights; `n_households`, `households_weighted`,
`people_weighted`, `uncovered_purchases_share`, `se_design` for the groups. Text values ("<20",
"suppressed") stay in `value_text` with no number. Standard library only: the store is built
without the microdata tools installed.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from traceconomics.checks import FormatError, require

# Bump when parsing changes in a way that changes the output: the store then re-parses.
PARSER_VERSION = "3"
# Files written before a dimension existed: weights before the spending concept hold all-modes
# shares; error bands before the tutoring option are for tutoring priced (the only option then).
DEFAULTS = {"spending": "all", "tutoring": "priced"}

FORMATS = {
    "oet-weights": {
        "dims": ("geo", "grouping", "group", "spending", "imputed_rent", "hh_weighting", "tutoring", "coicop18"),
        "measures": ("share", "se", "n_households_unweighted", "reliability"),
    },
    "oet-groups": {
        "dims": ("geo", "grouping", "group"),
        "measures": ("n_households", "households_weighted", "people_weighted", "uncovered_purchases_share",
                     "se_design"),
    },
    "oet-bands": {
        "dims": ("geo", "grouping", "group", "spending", "imputed_rent", "price_source", "weights_timing", "tutoring",
                 "unit"),
        "measures": ("se",),
        "period": "ref_period",
    },
}


def _number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def rows(path: Path, fmt: str):
    """(*dims, measure, ref_period, value_text, value) for every value in the file."""
    spec = FORMATS[fmt]
    text = Path(path).read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    reader = csv.DictReader(io.StringIO(body))
    period_col = spec.get("period", "ref_year")
    needed = {*spec["dims"], *spec["measures"], period_col}
    missing = needed - set(reader.fieldnames or ()) - set(DEFAULTS)
    require(not missing, f"{Path(path).name}: columns missing: {sorted(missing)}")
    seen = set()
    for row in reader:
        row = {**DEFAULTS, **row}
        key = tuple(row[d] for d in spec["dims"])
        period = row[period_col]
        require((key, period) not in seen, f"{Path(path).name}: duplicate row {key} {period}")
        seen.add((key, period))
        if not (period.isdigit() or (len(period) == 7 and period[4] == "-" and period.replace("-", "").isdigit())):
            raise FormatError(f"{Path(path).name}: {period_col} {period!r}")
        for m in spec["measures"]:
            value = row[m]
            if value == "":
                continue
            yield (*key, m, period, value, _number(value))
