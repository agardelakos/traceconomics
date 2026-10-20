"""The first published series, end to end: archive -> store -> engine -> CSV and metadata."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from traceconomics import references
from traceconomics.archive.store import Archive
from traceconomics.export import skeleton
from traceconomics.store.build import Store, update
from traceconomics.store.query import open_views

FIX = Path(__file__).parent / "fixtures"


def test_skeleton_export_from_a_store(tmp_path):
    archive = Archive(tmp_path / "archive")
    when = datetime(2026, 10, 18, 10, 0, tzinfo=UTC)
    for name in ("minr", "iw"):
        archive.store_bytes("eurostat", f"prc_hicp_{name}", (FIX / f"eurostat_v1_gr_{name}.tsv.gz").read_bytes(),
                            url="https://example.invalid", retrieved_at=when, ext=".tsv.gz",
                            extra={"eurostat_updated": "2026-10-16T23:00:00+0200"})
    con = duckdb.connect()
    store = Store(tmp_path / "store")
    update(archive, store, con, only=["eurostat:prc_hicp_minr", "eurostat:prc_hicp_iw"])
    open_views(con, store.root)

    csv_path, json_path = skeleton.export(con, tmp_path / "out")
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert rows[0]["period"] == "2015-01" and rows[-1]["period"] == "2026-09"
    gaps = [abs(float(r["annual_rate"]) - float(r["official_annual_rate"]))
            for r in rows if r["annual_rate"] and r["official_annual_rate"]]
    assert len(gaps) >= 100 and max(gaps) <= 0.1 + 1e-9

    meta = json.loads(json_path.read_text(encoding="utf-8"))
    assert meta["licence"] == "CC BY 4.0" and "Eurostat" in meta["attribution"]
    assert meta["sources"] and references.missing(meta["sources"]) == []
    assert meta["data_as_published_by"] == "2026-10-16T21:00Z"
