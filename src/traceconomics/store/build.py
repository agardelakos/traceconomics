"""Build the observation store from the raw archive.

Layout under the store folder (a cache: delete it and `traceconomics store rebuild` makes it again):

    observations/<source>.<dataset>/<n>-<sha>.parquet   one part per archived snapshot that changed anything
    labels/<source>.<dataset>.parquet                    code, label_en, label_el (where the source has labels)
    loaded.jsonl                                         every snapshot read: which, by which parser version, what it added

Every row is one value of one series for one period, as known from one
snapshot. A snapshot adds a row only where it differs from the previous
snapshot **of the same archived file**: a new or revised value, or a value
that disappeared (a `withdrawn` row). Comparing only within one archived file
matters because a dataset can be fed by many files (one per year for ELSTAT's
table 07): a 2010 file must not "withdraw" 2026 values it never had.

So "what did we know on date X" is the latest row per series and period
published or retrieved by X (see `query.py`), and nothing is ever lost.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from traceconomics.archive.store import Archive, read_jsonl
from traceconomics.catalog import DatasetSpec, datasets
from traceconomics.sources.elstat import parse as elstat_parse
from traceconomics.sources.elstat import table05 as elstat_table05
from traceconomics.sources import oet_local
from traceconomics.sources.eurostat import parse as eurostat_parse
from traceconomics.store.registry import Snapshot, label_files, snapshots

LOADED = "loaded.jsonl"
PARSERS = {"eurostat-tsv": eurostat_parse.PARSER_VERSION, "elstat-cpi07": elstat_parse.PARSER_VERSION,
           "elstat-cpi05": elstat_table05.PARSER_VERSION,
           **{fmt: oet_local.PARSER_VERSION for fmt in oet_local.FORMATS}}
COMMON_HEAD = ["dataset", "archive_dataset", "key"]
COMMON_TAIL = ["ref_period", "published_at", "published_at_quality", "retrieved_at", "value", "value_text",
               "status", "flags", "raw_sha256", "parser_version"]


@dataclass
class DatasetReport:
    dataset: str
    rebuilt: str | None = None          # why everything was re-read, if it was
    snapshots: int = 0                  # snapshots read this time
    added: int = 0                      # new or revised values
    withdrawn: int = 0
    skipped: list[str] = field(default_factory=list)

    def line(self) -> str:
        why = f" (re-read everything: {self.rebuilt})" if self.rebuilt else ""
        return (f"{self.dataset}: {self.snapshots} snapshot(s) read, {self.added:,} values added or revised, "
                f"{self.withdrawn:,} withdrawn{why}")


def folder_name(spec: DatasetSpec) -> str:
    return f"{spec.source}.{spec.name}"  # no ":" in Windows file names


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.observations = self.root / "observations"
        self.labels = self.root / "labels"
        for d in (self.observations, self.labels):
            d.mkdir(parents=True, exist_ok=True)

    def loaded(self, dataset_id: str | None = None) -> list[dict]:
        recs = read_jsonl(self.root / LOADED)
        return [r for r in recs if dataset_id is None or r["dataset"] == dataset_id]

    def _append_loaded(self, record: dict) -> None:
        with (self.root / LOADED).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def forget(self, dataset_id: str, folder: Path) -> None:
        """Drop a dataset's parts and its loaded records, before re-reading it."""
        for part in folder.glob("*.parquet"):
            part.unlink()
        keep = [r for r in self.loaded() if r["dataset"] != dataset_id]
        _write_atomic(self.root / LOADED, "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                                                  for r in keep))


def update(archive: Archive, store: Store, con: duckdb.DuckDBPyConnection, *,
           only: list[str] | None = None, full: bool = False) -> list[DatasetReport]:
    reports = []
    for spec in datasets().values():
        if only and spec.id not in only:
            continue
        reports.append(_update_dataset(archive, store, con, spec, full))
    return reports


def _update_dataset(archive: Archive, store: Store, con, spec: DatasetSpec, full: bool) -> DatasetReport:
    report = DatasetReport(spec.id)
    folder = store.observations / folder_name(spec)
    folder.mkdir(exist_ok=True)
    version = PARSERS[spec.format]
    feeds = snapshots(archive, spec)
    done = store.loaded(spec.id)

    reason = None
    if full:
        reason = "asked for"
    elif any(r["parser_version"] != version for r in done):
        reason = f"parser version changed to {version}"
    else:
        newest = {}
        for r in done:
            newest[r["archive_dataset"]] = max(newest.get(r["archive_dataset"], ""), r["retrieved_at"])
        seen = {(r["archive_dataset"], r["sha256"]) for r in done}
        for ad, snaps in feeds.items():
            if any((ad, s.sha256) not in seen and s.retrieved_at < newest.get(ad, "") for s in snaps):
                reason = f"an older snapshot of {ad} arrived after newer ones were read"
                break
    if reason:
        report.rebuilt = reason
        store.forget(spec.id, folder)
        done = []

    # A part written without its loaded record (a crash in between) would be counted twice.
    known_parts = {r.get("part") for r in done}
    for part in folder.glob("*.parquet"):
        if part.name not in known_parts:
            part.unlink()

    seen = {(r["archive_dataset"], r["sha256"]) for r in done}
    seq = len(done)
    for ad, snaps in sorted(feeds.items()):
        for snap in snaps:
            if (ad, snap.sha256) in seen:
                continue
            seq += 1
            added, withdrawn, part = _ingest(con, spec, snap, folder, seq, version)
            store._append_loaded({
                "dataset": spec.id, "archive_dataset": ad, "sha256": snap.sha256,
                "retrieved_at": snap.retrieved_at, "parser_version": version,
                "added": added, "withdrawn": withdrawn, "part": part,
                "loaded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            report.snapshots += 1
            report.added += added
            report.withdrawn += withdrawn
    if spec.label_files is not None and (report.snapshots or not (store.labels / f"{folder_name(spec)}.parquet").exists()):
        _write_labels(con, archive, store, spec)
    return report


def _parse_into(con, spec: DatasetSpec, snap: Snapshot, table: str) -> None:
    if spec.format == "eurostat-tsv":
        eurostat_parse.parse(con, snap.path, spec, table=table)
    elif spec.format == "elstat-cpi07":
        t = elstat_parse.parse(snap.path)
        con.execute(f"CREATE OR REPLACE TABLE {table} (freq VARCHAR, unit VARCHAR, coicop18 VARCHAR, geo VARCHAR, "
                    "ref_period VARCHAR, value_text VARCHAR, value DOUBLE, flags VARCHAR)")
        con.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, 'GR', ?, ?, ?, NULL)",
                        [(f, u, c, p, repr(v), v) for f, u, c, p, v in t.rows()])
    elif spec.format == "elstat-cpi05":
        t5 = elstat_table05.parse(snap.path)
        con.execute(f"CREATE OR REPLACE TABLE {table} (freq VARCHAR, unit VARCHAR, geo VARCHAR, "
                    "ref_period VARCHAR, value_text VARCHAR, value DOUBLE, flags VARCHAR)")
        con.executemany(f"INSERT INTO {table} VALUES (?, ?, 'GR', ?, ?, ?, NULL)",
                        [(f, u, p, repr(v), v) for f, u, p, v in t5.rows()])
    elif spec.format in oet_local.FORMATS:
        dims = oet_local.FORMATS[spec.format]["dims"]
        cols = ", ".join(f'"{d}" VARCHAR' for d in (*dims, "measure"))
        con.execute(f"CREATE OR REPLACE TABLE {table} ({cols}, ref_period VARCHAR, value_text VARCHAR, "
                    "value DOUBLE, flags VARCHAR)")
        con.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * (len(dims) + 4))}, NULL)",
                        list(oet_local.rows(snap.path, spec.format)))
    else:
        raise ValueError(f"no parser for {spec.format}")


def _ingest(con, spec: DatasetSpec, snap: Snapshot, folder: Path, seq: int, version: str):
    dims = list(spec.dimensions)
    _parse_into(con, spec, snap, "new_raw")
    # Dimension names are quoted: some are SQL words ("group").
    key = " || ',' || ".join(f"'{d}=' || \"{d}\"" for d in dims)
    con.execute(f"CREATE OR REPLACE TEMP TABLE new AS SELECT {key} AS key, * FROM new_raw")
    con.execute("DROP TABLE new_raw")

    parts = sorted(folder.glob("*.parquet"))
    if parts:
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE cur AS
            SELECT * FROM read_parquet('{(folder / '*.parquet').as_posix()}', union_by_name = true)
            WHERE archive_dataset = ?
            QUALIFY row_number() OVER (PARTITION BY key, ref_period ORDER BY retrieved_at DESC) = 1
        """, [snap.archive_dataset])
        con.execute("DELETE FROM cur WHERE status = 'withdrawn'")
    else:
        cols = ", ".join(f'NULL::VARCHAR AS "{c}"' for c in ["key", *dims, "ref_period", "value_text", "flags"])
        con.execute(f"CREATE OR REPLACE TEMP TABLE cur AS SELECT {cols} WHERE false")

    updated = snap.manifest.get("eurostat_updated")
    published_at = _utc(updated) if updated else _utc(snap.retrieved_at)
    quality = "dataset" if updated else "first_seen"
    retrieved_at = _utc(snap.retrieved_at)
    backcast = f"ref_period < '{spec.backcast_before}'" if spec.backcast_before else "false"
    flash = f"{spec.release} = 'FLS'" if spec.release else "false"
    status = (f"CASE WHEN gone THEN 'withdrawn' WHEN {backcast} THEN 'backcast' WHEN {flash} THEN 'flash' "
              "WHEN coalesce(flags, '') LIKE '%p%' THEN 'provisional' ELSE 'final' END")
    dim_cols = ", ".join(f'"{d}"' for d in dims)
    params = [spec.id, snap.archive_dataset, published_at, quality, retrieved_at, snap.sha256, version]
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE out AS
        SELECT ?::VARCHAR AS dataset, ?::VARCHAR AS archive_dataset, key, {dim_cols}, ref_period,
               ?::TIMESTAMP AS published_at, ?::VARCHAR AS published_at_quality, ?::TIMESTAMP AS retrieved_at,
               value, value_text, {status} AS status, flags, ?::VARCHAR AS raw_sha256, ?::VARCHAR AS parser_version
        FROM (
            -- new or revised: no earlier row, or a different value or flags (missing values compare equal)
            SELECT n.*, false AS gone FROM new n LEFT JOIN cur c ON c.key = n.key AND c.ref_period = n.ref_period
            WHERE c.key IS NULL
               OR c.value_text IS DISTINCT FROM n.value_text
               OR c.flags IS DISTINCT FROM n.flags
            UNION ALL BY NAME
            -- withdrawn: in the previous snapshot of this file, not in this one
            SELECT c.key, {', '.join(f'c."{d}"' for d in dims)}, c.ref_period,
                   NULL::VARCHAR AS value_text, NULL::DOUBLE AS value, NULL::VARCHAR AS flags, true AS gone
            FROM cur c ANTI JOIN new n ON c.key = n.key AND c.ref_period = n.ref_period
        )
    """, params)
    added, withdrawn = con.execute(
        "SELECT count(*) FILTER (WHERE status <> 'withdrawn'), count(*) FILTER (WHERE status = 'withdrawn') FROM out"
    ).fetchone()
    part = None
    if added or withdrawn:
        part = f"{seq:05d}-{snap.sha256[:12]}.parquet"
        tmp = folder / (part + ".part")
        con.execute(f"COPY out TO '{tmp.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
        os.replace(tmp, folder / part)
    for t in ("new", "cur", "out"):
        con.execute(f"DROP TABLE IF EXISTS {t}")
    return added, withdrawn, part


def _write_labels(con, archive: Archive, store: Store, spec: DatasetSpec) -> None:
    """Labels from the newest file of each language (later years override earlier ones)."""
    labels: dict[str, dict[str, str]] = {}
    for path in label_files(archive, spec):
        if spec.format != "elstat-cpi07":
            continue
        t = elstat_parse.parse(path)
        for code, label in t.labels.items():
            labels.setdefault(code, {})[t.language] = label
    con.execute("CREATE OR REPLACE TEMP TABLE lab (code VARCHAR, label_en VARCHAR, label_el VARCHAR)")
    con.executemany("INSERT INTO lab VALUES (?, ?, ?)",
                    [(c, v.get("en"), v.get("el")) for c, v in sorted(labels.items())])
    path = store.labels / f"{folder_name(spec)}.parquet"
    tmp = path.with_name(path.name + ".part")
    con.execute(f"COPY lab TO '{tmp.as_posix()}' (FORMAT parquet)")
    os.replace(tmp, path)
    con.execute("DROP TABLE lab")
