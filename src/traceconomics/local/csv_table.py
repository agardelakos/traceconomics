"""Our survey tables as CSV: `#` lines first (what the table is, its provenance), then the rows.

Shared by `weights run` and `silc run`, so both write numbers the same way; a change here changes
both kinds of table, and both fingerprints cover this file.
"""

from __future__ import annotations

import csv
import io

import numpy as np
import pandas as pd


def _num(x, digits: int = 10) -> str:
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{digits}g}"


def to_csv(table: pd.DataFrame, header: list[str]) -> bytes:
    out = io.StringIO()
    for line in header:
        out.write(f"# {line}\n")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(table.columns)
    for row in table.itertuples(index=False):
        w.writerow(
            [_num(v) if isinstance(v, (float, np.floating)) else ("" if v is pd.NA or v is None else v) for v in row]
        )
    return out.getvalue().encode("utf-8")
