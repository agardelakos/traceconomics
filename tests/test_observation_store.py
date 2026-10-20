"""The observation store: built from an archive, diffs within one archived file, incremental = full."""

import gzip
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from traceconomics.archive.store import Archive
from traceconomics.store import build
from traceconomics.store.build import Store, update
from traceconomics.store.query import as_of, open_views

FIX = Path(__file__).parent / "fixtures"
MINR = "eurostat:prc_hicp_minr"
T1 = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)
GR_TOTAL = "freq=M,unit=I25,coicop18=TOTAL,geo=GR"


def minr_text() -> str:
    return gzip.decompress((FIX / "eurostat_prc_hicp_minr.tsv.gz").read_bytes()).decode("utf-8")


def revised(text: str) -> str:
    """A second snapshot: Greek all-items 2026-08 revised, and Cyprus food (CP01) withdrawn."""
    lines = text.splitlines(keepends=True)
    out = []
    for line in lines:
        key = line.split("\t", 1)[0]
        if key == "M,I25,CP01,CY":
            continue
        if key == "M,I25,TOTAL,EL":
            line = line.replace("104.12 ", "104.20 ")
        out.append(line)
    return "".join(out)


def put_minr(archive: Archive, text: str, when: datetime, updated: str):
    return archive.store_bytes("eurostat", "prc_hicp_minr", gzip.compress(text.encode("utf-8")),
                               url="https://example.invalid/minr", retrieved_at=when, ext=".tsv.gz",
                               extra={"eurostat_updated": updated})


def put_cpi07(archive: Archive, name: str, doc: str, when: datetime):
    archive.store_bytes("elstat", doc, (FIX / name).read_bytes(), url="https://example.invalid/doc",
                        retrieved_at=when, ext=Path(name).suffix,
                        extra={"original_name": f"A0515_DKT87_TS_MM_01_{name[13:17]}_12_{name[13:17]}_07_F_EN{Path(name).suffix}"})


@pytest.fixture
def con():
    c = duckdb.connect()
    yield c
    c.close()


def rows(con, store_root, sql):
    open_views(con, store_root)
    return con.execute(sql).fetchall()


def test_first_load_then_a_revision_and_a_withdrawal(tmp_path, con):
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")
    first = update(archive, store, con, only=[MINR])[0]
    assert first.snapshots == 1 and first.added > 1000 and first.withdrawn == 0

    put_minr(archive, revised(minr_text()), T2, "2026-10-15T23:00:00+0200")
    second = update(archive, store, con, only=[MINR])[0]
    cy_food = rows(con, store.root, "SELECT count(*) FROM observations WHERE key = "
                   "'freq=M,unit=I25,coicop18=01,geo=CY'")[0][0]
    assert second.snapshots == 1 and second.added == 1 and second.withdrawn == cy_food // 2

    # What was known before and after the revision.
    before = as_of(con, MINR, datetime(2026, 10, 1), where=f"key = '{GR_TOTAL}' AND ref_period = '2026-08'")
    after = as_of(con, MINR, None, where=f"key = '{GR_TOTAL}' AND ref_period = '2026-08'")
    assert before.fetchall()[0][before.columns.index("value_text")] == "104.12"
    assert after.fetchall()[0][after.columns.index("value_text")] == "104.20"
    # The withdrawn series is gone now, but was there before.
    assert not as_of(con, MINR, None, where="geo = 'CY' AND coicop18 = '01' AND unit = 'I25'").fetchall()
    assert as_of(con, MINR, datetime(2026, 10, 1), where="geo = 'CY' AND coicop18 = '01' AND unit = 'I25'").fetchall()

    # Nothing new in the archive: nothing read.
    assert update(archive, store, con, only=[MINR])[0].snapshots == 0


def test_vintage_dates_and_status(tmp_path, con):
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")
    update(archive, store, con, only=[MINR])
    (pub, quality, status_2025, status_2026), = rows(con, store.root, f"""
        SELECT any_value(published_at), any_value(published_at_quality),
               any_value(status) FILTER (WHERE ref_period = '2025-12'),
               any_value(status) FILTER (WHERE ref_period = '2026-01')
        FROM observations WHERE key = '{GR_TOTAL}'""")
    assert pub == datetime(2026, 9, 16, 21, 0) and quality == "dataset"   # Eurostat's update time, in UTC
    assert (status_2025, status_2026) == ("backcast", "final")


def test_incremental_equals_full_rebuild(tmp_path, con):
    archive = Archive(tmp_path / "a")
    inc, full = Store(tmp_path / "inc"), Store(tmp_path / "full")
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")
    update(archive, inc, con, only=[MINR])
    put_minr(archive, revised(minr_text()), T2, "2026-10-15T23:00:00+0200")
    update(archive, inc, con, only=[MINR])
    update(archive, full, con, only=[MINR], full=True)
    q = "SELECT * EXCLUDE (published_at) FROM observations ORDER BY ALL"
    assert rows(con, inc.root, q) == rows(duckdb.connect(), full.root, q)


def test_two_files_feed_one_dataset_without_withdrawing_each_other(tmp_path, con):
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_cpi07(archive, "elstat_cpi07_2025.xls", "doc-554284", T1)
    put_cpi07(archive, "elstat_cpi07_2026.xlsx", "doc-585819", T2)
    r = update(archive, store, con, only=["elstat:cpi07"])[0]
    assert r.snapshots == 2 and r.withdrawn == 0
    # December 2025 comes from both files: as a month of 2025 and as 2026's link month.
    (n,), = rows(con, store.root, "SELECT count(DISTINCT archive_dataset) FROM observations "
                 "WHERE coicop18 = 'TOTAL' AND ref_period = '2025-12'")
    assert n == 2
    (en, el), = con.execute("SELECT label_en, label_el FROM labels WHERE code = '01111'").fetchall()
    assert en.strip() == "CEREALS" and el is None   # no Greek file in this archive


def test_older_snapshot_arriving_late_rebuilds(tmp_path, con):
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, revised(minr_text()), T2, "2026-10-15T23:00:00+0200")
    update(archive, store, con, only=[MINR])
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")   # e.g. seeded from an older download
    r = update(archive, store, con, only=[MINR])[0]
    assert r.rebuilt and "older snapshot" in r.rebuilt and r.snapshots == 2


def test_parser_change_rebuilds(tmp_path, con, monkeypatch):
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")
    update(archive, store, con, only=[MINR])
    monkeypatch.setitem(build.PARSERS, "eurostat-tsv", "2")
    r = update(archive, store, con, only=[MINR])[0]
    assert r.rebuilt and "parser version" in r.rebuilt and r.snapshots == 1


def test_part_without_a_loaded_record_is_dropped(tmp_path, con):
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")
    update(archive, store, con, only=[MINR])
    folder = store.observations / "eurostat.prc_hicp_minr"
    part = next(folder.glob("*.parquet"))
    (folder / "99999-orphan.parquet").write_bytes(part.read_bytes())   # as if a crash came before logging
    update(archive, store, con, only=[MINR])
    assert not (folder / "99999-orphan.parquet").exists()


def test_as_of_rows_come_in_a_fixed_order(tmp_path):
    # Parallel reads return rows in any order; sums over them must not depend on it.
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")
    results = []
    for threads in (1, 4):
        c = duckdb.connect(config={"threads": threads})
        update(archive, store, c, only=[MINR])
        open_views(c, store.root)
        rel = as_of(c, MINR)
        results.append(rel.project("key, ref_period").fetchall())
        c.close()
    assert results[0] == results[1] == sorted(results[0]) and len(results[0]) > 1000


def test_label_files_come_only_from_the_datasets_the_store_reads(tmp_path):
    # An old table kept elsewhere in the archive for another purpose has a name the label
    # pattern matches, but another format: it must not be read for labels.
    from traceconomics import catalog
    from traceconomics.store.registry import label_files

    archive = Archive(tmp_path / "a")
    for dataset, name in (("doc-457128-el", "457128_el__A0515_DKT87_TS_MM_01_2022_12_2022_07_F_GR.xls"),
                          ("cpi07-original-2008", "A0515_DKT87_TS_MM_01_2008_12_2008_07_F_GR.xls")):
        archive.store_bytes("elstat", dataset, name.encode(), url=None, retrieved_at=T1, ext=".xls",
                            kind="manual", extra={"original_name": name})
    found = label_files(archive, catalog.dataset("elstat:cpi07"))
    assert [p.parts[-3] for p in found] == ["doc-457128-el"]
