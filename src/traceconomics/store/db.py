"""DuckDB connections with bounded memory.

Uncapped, DuckDB takes most of the free memory. That's fine on a large
laptop but not on a small CI runner, so every connection is capped; DuckDB
spills to disk beyond the cap. Measured on the largest Eurostat file
(22.5 million values): 2 GB and 4 threads cost about 15% in time.
"""

from __future__ import annotations

import duckdb

DEFAULT_MEMORY_LIMIT = "2GB"


def connect(memory_limit: str = DEFAULT_MEMORY_LIMIT, threads: int | None = None) -> duckdb.DuckDBPyConnection:
    config = {"memory_limit": memory_limit}
    if threads:
        config["threads"] = threads
    con = duckdb.connect(config=config)
    con.execute("SET enable_progress_bar = false")  # a session setting, refused in `config`
    return con
