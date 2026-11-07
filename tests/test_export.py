"""The first published series, end to end: archive -> store -> engine -> CSV and metadata."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from traceconomics import references
from traceconomics.archive.store import Archive
from traceconomics.export import skeleton
from traceconomics.store.build import Store, update
from traceconomics.store.query import open_views

pytestmark = pytest.mark.integration

FIX = Path(__file__).parent / "fixtures"


def test_skeleton_export_from_a_store(tmp_path):
    """PY-EXPORT-001: the first series is exported from the store with its metadata

    Given an archive holding the Eurostat HICP monthly rates and item weights for Greece
    And a store updated from those two datasets
    When the skeleton series is exported
    Then the CSV runs from 2015-01 to 2026-09
    And at least 100 months have both our annual rate and the official one, and no gap between them exceeds 0.1 points
    And the metadata gives the CC BY 4.0 licence and attributes Eurostat
    And every source it lists is in the bibliography
    And it states the data as published by Eurostat, in UTC (2026-10-16T21:00Z)
    """
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
