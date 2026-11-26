"""The observation store: built from an archive, diffs within one archived file, incremental = full."""

import gzip
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from traceconomics.archive.store import Archive
from traceconomics.store import build
from traceconomics.store.build import Store, update
from traceconomics.store.query import as_of, open_views

pytestmark = pytest.mark.integration

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
    return archive.store_bytes(
        "eurostat",
        "prc_hicp_minr",
        gzip.compress(text.encode("utf-8")),
        url="https://example.invalid/minr",
        retrieved_at=when,
        ext=".tsv.gz",
        extra={"eurostat_updated": updated},
    )


def put_cpi07(archive: Archive, name: str, doc: str, when: datetime):
    archive.store_bytes(
        "elstat",
        doc,
        (FIX / name).read_bytes(),
        url="https://example.invalid/doc",
        retrieved_at=when,
        ext=Path(name).suffix,
        extra={"original_name": f"A0515_DKT87_TS_MM_01_{name[13:17]}_12_{name[13:17]}_07_F_EN{Path(name).suffix}"},
    )


@pytest.fixture
def con():
    c = duckdb.connect()
    yield c
    c.close()


def rows(con, store_root, sql):
    open_views(con, store_root)
    return con.execute(sql).fetchall()


def test_first_load_then_a_revision_and_a_withdrawal(tmp_path, con):
    """PY-OBS-001: a first load, then a revision and a withdrawal

    Given an archive with one snapshot of Eurostat's HICP monthly indices
    When the store is updated
    And a second snapshot is archived with Greece's 2026-08 all-items index revised and Cyprus's food series withdrawn
    And the store is updated again, queried as of 2026-10-01 and as of now, and then updated once more with nothing new
    Then the first update reads 1 snapshot, adds more than 1000 rows and withdraws none
    And the second reads 1 snapshot, adds 1 row and withdraws every Cyprus food observation (half the rows stored under its key)
    And as of 2026-10-01 Greece's 2026-08 value is "104.12", and as of now "104.20"
    And the withdrawn series is missing as of now but present as of 2026-10-01
    And the last update reads no snapshot
    """
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")
    first = update(archive, store, con, only=[MINR])[0]
    assert first.snapshots == 1 and first.added > 1000 and first.withdrawn == 0

    put_minr(archive, revised(minr_text()), T2, "2026-10-15T23:00:00+0200")
    second = update(archive, store, con, only=[MINR])[0]
    cy_food = rows(
        con, store.root, "SELECT count(*) FROM observations WHERE key = 'freq=M,unit=I25,coicop18=01,geo=CY'"
    )[0][0]
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
    """PY-OBS-002: observations carry their publication time, its quality and their status

    Given an archive with one HICP snapshot whose Eurostat update time is 2026-09-16 23:00 +02:00
    When the store is updated
    Then Greece's all-items rows are published at 2026-09-16 21:00 UTC, with quality "dataset"
    And 2025-12 is "backcast" and 2026-01 "final"
    """
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")
    update(archive, store, con, only=[MINR])
    ((pub, quality, status_2025, status_2026),) = rows(
        con,
        store.root,
        f"""
        SELECT any_value(published_at), any_value(published_at_quality),
               any_value(status) FILTER (WHERE ref_period = '2025-12'),
               any_value(status) FILTER (WHERE ref_period = '2026-01')
        FROM observations WHERE key = '{GR_TOTAL}'""",
    )
    assert pub == datetime(2026, 9, 16, 21, 0) and quality == "dataset"  # Eurostat's update time, in UTC
    assert (status_2025, status_2026) == ("backcast", "final")


def test_incremental_equals_full_rebuild(tmp_path, con):
    """PY-OBS-003: an incremental store equals a full rebuild

    Given an archive with two HICP snapshots
    When one store is updated after each snapshot
    And another is rebuilt in full from both
    Then both hold the same observations, publication time aside
    """
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
    """PY-OBS-004: two files feed one dataset without withdrawing each other

    Given an archive with CPI table 07 for 2025 and for 2026, each its own archive dataset
    When the store is updated for elstat:cpi07
    Then it reads 2 snapshots and withdraws nothing
    And December 2025's all-items index comes from both files (as a month of 2025 and as 2026's link month)
    And the English label of 01111 is "CEREALS" and the Greek one is missing, since no Greek file is archived
    """
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_cpi07(archive, "elstat_cpi07_2025.xls", "doc-554284", T1)
    put_cpi07(archive, "elstat_cpi07_2026.xlsx", "doc-585819", T2)
    r = update(archive, store, con, only=["elstat:cpi07"])[0]
    assert r.snapshots == 2 and r.withdrawn == 0
    # December 2025 comes from both files: as a month of 2025 and as 2026's link month.
    ((n,),) = rows(
        con,
        store.root,
        "SELECT count(DISTINCT archive_dataset) FROM observations WHERE coicop18 = 'TOTAL' AND ref_period = '2025-12'",
    )
    assert n == 2
    ((en, el),) = con.execute("SELECT label_en, label_el FROM labels WHERE code = '01111'").fetchall()
    assert en.strip() == "CEREALS" and el is None  # no Greek file in this archive


def test_table05_english_file_only(tmp_path, con):
    """PY-OBS-005: table 05 is read from the English file only

    Given an archive with CPI table 05 in English and in Greek
    When the store is updated for elstat:cpi05
    Then it reads 1 snapshot
    And the 2026-09 twelve-month rate is stored at full precision, as value and as text (0.05049184623573861)
    """
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    data = (FIX / "elstat_cpi05_2026_09.xlsx").read_bytes()
    for doc, lang in (("doc-114837", "EN"), ("doc-114837-el", "GR")):
        archive.store_bytes(
            "elstat",
            doc,
            data,
            url="https://example.invalid/doc",
            retrieved_at=T1,
            ext=".xlsx",
            extra={"original_name": f"114837__A0515_DKT87_TS_MM_01_1959_09_2026_05_F_{lang}.xlsx"},
        )
    r = update(archive, store, con, only=["elstat:cpi05"])[0]
    assert r.snapshots == 1
    ((value, text),) = rows(
        con,
        store.root,
        "SELECT value, value_text FROM observations WHERE unit = 'RCH_A_FR' AND freq = 'M' AND ref_period = '2026-09'",
    )
    assert value == 0.05049184623573861 and text == "0.05049184623573861"


def test_older_snapshot_arriving_late_rebuilds(tmp_path, con):
    """PY-OBS-006: an older snapshot arriving late rebuilds the dataset

    Given a store updated from the newer HICP snapshot
    When an older snapshot is archived and the store is updated
    Then the dataset is rebuilt, the reason naming the "older snapshot"
    And both snapshots are read
    """
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, revised(minr_text()), T2, "2026-10-15T23:00:00+0200")
    update(archive, store, con, only=[MINR])
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")  # e.g. seeded from an older download
    r = update(archive, store, con, only=[MINR])[0]
    assert r.rebuilt and "older snapshot" in r.rebuilt and r.snapshots == 2


def test_parser_change_rebuilds(tmp_path, con, monkeypatch):
    """PY-OBS-007: a parser change rebuilds the dataset

    Given a store updated from one HICP snapshot
    When the Eurostat TSV parser's version changes and the store is updated
    Then the dataset is rebuilt, the reason naming the "parser version"
    And 1 snapshot is read
    """
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")
    update(archive, store, con, only=[MINR])
    monkeypatch.setitem(build.PARSERS, "eurostat-tsv", "2")
    r = update(archive, store, con, only=[MINR])[0]
    assert r.rebuilt and "parser version" in r.rebuilt and r.snapshots == 1


def test_part_without_a_loaded_record_is_dropped(tmp_path, con):
    """PY-OBS-008: a store part without a loaded record is dropped

    Given a store updated from one HICP snapshot
    And an extra Parquet part with no record in loaded.jsonl, as if a crash came before logging
    When the store is updated
    Then the extra part is deleted
    """
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")
    update(archive, store, con, only=[MINR])
    folder = store.observations / "eurostat.prc_hicp_minr"
    part = next(folder.glob("*.parquet"))
    (folder / "99999-orphan.parquet").write_bytes(part.read_bytes())  # as if a crash came before logging
    update(archive, store, con, only=[MINR])
    assert not (folder / "99999-orphan.parquet").exists()


def test_as_of_rows_come_in_a_fixed_order(tmp_path):
    # Parallel reads return rows in any order; sums over them must not depend on it.
    """PY-OBS-009: as-of rows come in a fixed order

    Given an archive with one HICP snapshot
    When the store is updated and read as of now on a 1-thread and a 4-thread connection
    Then both give the same keys and periods, in sorted order
    And there are more than 1000 rows

    Parallel reads return rows in any order; sums over them must not depend on it.
    """
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
    """PY-OBS-010: label files come only from the datasets the store reads

    Given an archive with a Greek table 07 document and an old original table whose file name the label pattern also matches
    When the label files for elstat:cpi07 are listed
    Then only the Greek table 07 document is listed

    An old table kept elsewhere in the archive for another purpose has a name the label
    pattern matches, but another format: it must not be read for labels.
    """
    from traceconomics import catalog
    from traceconomics.store.registry import label_files

    archive = Archive(tmp_path / "a")
    for dataset, name in (
        ("doc-457128-el", "457128_el__A0515_DKT87_TS_MM_01_2022_12_2022_07_F_GR.xls"),
        ("cpi07-original-2008", "A0515_DKT87_TS_MM_01_2008_12_2008_07_F_GR.xls"),
    ):
        archive.store_bytes(
            "elstat",
            dataset,
            name.encode(),
            url=None,
            retrieved_at=T1,
            ext=".xls",
            kind="manual",
            extra={"original_name": name},
        )
    found = label_files(archive, catalog.dataset("elstat:cpi07"))
    assert [p.parts[-3] for p in found] == ["doc-457128-el"]


def test_update_without_table_07_writes_empty_labels(tmp_path, con):
    """PY-OBS-015: a store update with no CPI table 07 archived writes an empty labels file

    Given an archive that holds Eurostat's HICP monthly indices but no CPI table 07
    When the store is updated for both datasets
    Then it reads one snapshot of the HICP and none of table 07, and doesn't fail
    And the labels view exists and holds nothing
    """
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    put_minr(archive, minr_text(), T1, "2026-09-16T23:00:00+0200")
    reports = update(archive, store, con, only=[MINR, "elstat:cpi07"])
    assert sorted((r.dataset, r.snapshots) for r in reports) == [("elstat:cpi07", 0), (MINR, 1)]
    assert rows(con, store.root, "SELECT count(*) FROM labels") == [(0,)]


TRICKY = [
    ("plain", "", 0.1 + 0.2, None),  # an empty string, a float that isn't its short form, a missing value
    ('a "quote", a comma', "line\nbreak", -0.0, "p"),
    ("Ελληνικά", "\\N", 1e-300, ""),  # a field that reads like a null marker, the smallest floats
    (None, "NULL", 123456789.123456789, None),
    ("x", "y", float("inf"), "e"),
]


COLUMNS = [("a", "VARCHAR"), ("b", "VARCHAR"), ("value", "DOUBLE"), ("flags", "VARCHAR")]


def test_bulk_load_stores_what_a_row_by_row_insert_stores():
    """PY-OBS-011: the store's bulk load keeps every value exactly as a row-by-row insert does

    Given rows with empty strings, missing values, quotes, commas, line breaks and Greek text
    And fields reading "\\N" or "NULL", negative zero, a tiny float, infinity and a float not in its short form
    When they are loaded in bulk and, separately, inserted one row at a time
    Then both tables hold the same rows, in the same order, with the same types
    And an empty string stays an empty string while a missing value is NULL
    """
    con = duckdb.connect()
    build._load(con, "bulk", COLUMNS, iter(TRICKY))
    con.execute("CREATE TABLE one (a VARCHAR, b VARCHAR, value DOUBLE, flags VARCHAR)")
    con.executemany("INSERT INTO one VALUES (?, ?, ?, ?)", TRICKY)
    bulk = con.execute("SELECT * FROM bulk").fetchall()
    assert bulk == con.execute("SELECT * FROM one").fetchall()
    assert [str(v) for _, _, v, _ in bulk] == [str(v) for _, _, v, _ in TRICKY]  # -0.0 keeps its sign
    assert con.execute("SELECT count(*) FROM bulk WHERE b = ''").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM bulk WHERE flags IS NULL").fetchone()[0] == 2
    assert con.execute("DESCRIBE bulk").fetchall() == con.execute("DESCRIBE one").fetchall()


def test_bulk_load_of_no_rows_leaves_an_empty_table():
    """PY-OBS-012: a bulk load of no rows still makes the table, empty

    Given no rows (a survey table that can't be built for its year)
    When they are loaded in bulk
    Then the table exists with its columns and holds nothing
    """
    con = duckdb.connect()
    build._load(con, "empty", COLUMNS, iter([]))
    assert con.execute("SELECT count(*) FROM empty").fetchone()[0] == 0
    assert [r[0] for r in con.execute("DESCRIBE empty").fetchall()] == ["a", "b", "value", "flags"]


@pytest.mark.unit
def test_forgetting_a_dataset_rewrites_the_loaded_records_durably(tmp_path, monkeypatch):
    """PY-OBS-013: forgetting a dataset rewrites the loaded records to disk before they replace the old ones

    Given a store whose loaded records name two datasets
    When one of them is forgotten
    Then the records left are the other dataset's
    And the new file is synced to disk before it takes the old one's place, as every other write of it is
    """
    store = Store(tmp_path / "store")
    store._append_loaded({"dataset": "a:x", "seq": 1})
    store._append_loaded({"dataset": "b:y", "seq": 1})
    calls = []
    monkeypatch.setattr(build.os, "fsync", lambda fd: calls.append("fsync"))
    real_replace = build.os.replace
    monkeypatch.setattr(build.os, "replace", lambda a, b: (calls.append("replace"), real_replace(a, b)))
    (tmp_path / "folder").mkdir()
    store.forget("a:x", tmp_path / "folder")
    assert [r["dataset"] for r in store.loaded()] == ["b:y"]
    assert calls == ["fsync", "replace"]


def big_minr(drop: str | None = None) -> str:
    """A made-up HICP file of 360,000 values: large enough that DuckDB works on it in parallel."""
    periods = [f"{y}-{m:02d}" for y in range(1996, 2026) for m in range(1, 13)]
    lines = ["freq,unit,coicop18,geo\\TIME_PERIOD\t" + "\t".join(f"{p} " for p in periods)]
    for g, geo in enumerate(["EL", "CY", "DE", "FR", "IT", "ES", "PT", "AT"]):
        for u in range(5):
            for c in range(25):
                key = f"M,U{u},CP{c:02d},{geo}"
                if key != drop:
                    values = (f"{100 + (g * c + u + i) % 50}.{i % 100:02d} " for i in range(len(periods)))
                    lines.append(f"{key}\t" + "\t".join(values))
    return "\n".join(lines) + "\n"


def test_the_same_snapshots_write_the_same_part_bytes(tmp_path):
    """PY-OBS-014: the same snapshots write byte-identical store parts, whatever the threads

    Given an archive with two snapshots of a 360,000-value HICP file, the second without one series
    When the store is rebuilt in full on 1, 4, 4 and 8 threads
    Then every rebuild writes the same parts with the same SHA-256
    And the rows in each part are sorted by key and period

    Two builds of the store can only be compared by hash if the bytes don't depend on the
    order a parallel join happens to return rows in.
    """
    archive = Archive(tmp_path / "a")
    put_minr(archive, big_minr(), T1, "2026-09-16T23:00:00+0200")
    put_minr(archive, big_minr(drop="M,U2,CP07,CY"), T2, "2026-10-15T23:00:00+0200")
    hashes = []
    for i, threads in enumerate((1, 4, 4, 8)):
        store = Store(tmp_path / f"s{i}")
        c = duckdb.connect(config={"threads": threads})
        update(archive, store, c, only=[MINR], full=True)
        c.close()
        parts = sorted((store.root / "observations").rglob("*.parquet"))
        hashes.append({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in parts})
    assert len(hashes[0]) == 2 and all(h == hashes[0] for h in hashes)
    c = duckdb.connect(config={"threads": 1})
    for part in parts:
        keys = c.execute(f"SELECT key, ref_period FROM read_parquet('{part.as_posix()}')").fetchall()
        assert keys == sorted(keys)
