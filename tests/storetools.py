"""An in-memory observation store for unit tests: the `observations` table the store's views
expose, with the columns the module 1 queries read."""

from datetime import datetime

import duckdb

COLUMNS = ("dataset", "archive_dataset", "key", "unit", "freq", "coicop", "coicop18", "geo", "ref_period", "value")


def store(rows):
    """An in-memory `observations` table; each row a dict of COLUMNS (missing ones are NULL)."""
    con = duckdb.connect()
    con.execute("CREATE TABLE observations (dataset VARCHAR, archive_dataset VARCHAR, key VARCHAR, unit VARCHAR, "
                "freq VARCHAR, coicop VARCHAR, coicop18 VARCHAR, geo VARCHAR, ref_period VARCHAR, value DOUBLE, "
                "status VARCHAR, published_at TIMESTAMP, retrieved_at TIMESTAMP)")
    t = datetime(2026, 10, 1)
    con.executemany(f"INSERT INTO observations VALUES ({', '.join('?' * len(COLUMNS))}, 'final', ?, ?)",
                    [tuple(r.get(c) for c in COLUMNS) + (t, t) for r in rows])
    return con


def months(*years):
    return [f"{y}-{m:02d}" for y in years for m in range(1, 13)]
