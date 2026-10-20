"""Reading the store: every row, or what was known on a given date."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb


def open_views(con: duckdb.DuckDBPyConnection, store_root: Path) -> None:
    """Views `observations` (every row of every dataset) and `labels`."""
    obs = Path(store_root) / "observations"
    if not any(obs.glob("*/*.parquet")):
        raise FileNotFoundError(f"the store at {store_root} is empty; run `traceconomics store update`")
    con.execute(f"CREATE OR REPLACE VIEW observations AS SELECT * FROM read_parquet("
                f"'{(obs / '*' / '*.parquet').as_posix()}', union_by_name = true)")
    labels = Path(store_root) / "labels"
    if any(labels.glob("*.parquet")):
        con.execute(f"CREATE OR REPLACE VIEW labels AS SELECT * FROM read_parquet("
                    f"'{(labels / '*.parquet').as_posix()}', union_by_name = true, filename = true)")


def as_of(con: duckdb.DuckDBPyConnection, dataset: str, when: datetime | None = None,
          *, by: str = "published_at", where: str = "") -> duckdb.DuckDBPyRelation:
    """The latest value per series and period of `dataset`, as known at `when` (UTC; None = now).

    `by="published_at"` answers "what had the source published by then?";
    `by="retrieved_at"` answers "what did our pipeline have by then?".
    `where` adds an SQL condition, e.g. "geo = 'GR' AND unit = 'I25'".
    Withdrawn values are left out. Rows come sorted by key and period, so anything summed over them
    is summed in the same order on every run (parallel reads would otherwise vary it).
    """
    if by not in ("published_at", "retrieved_at"):
        raise ValueError("by must be published_at or retrieved_at")
    cond = ["dataset = $dataset"]
    params: dict = {"dataset": dataset}
    if when is not None:
        cond.append(f"{by} <= $when")
        params["when"] = when
    if where:
        cond.append(f"({where})")
    sql = f"""
        SELECT * EXCLUDE (rn) FROM (
            SELECT *, row_number() OVER (PARTITION BY key, ref_period
                                         ORDER BY {by} DESC, retrieved_at DESC) AS rn
            FROM observations WHERE {' AND '.join(cond)}
        ) WHERE rn = 1 AND status <> 'withdrawn'
        ORDER BY key, ref_period
    """
    return con.query(sql, params=params)
