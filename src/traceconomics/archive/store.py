"""Append-only storage for raw source files.

Layout under the archive root:

    raw/{source}/{dataset}/{stamp}/payload{.ext}   bytes exactly as received
    raw/{source}/{dataset}/{stamp}/manifest.json   where, when and how they were fetched
    raw/index.jsonl                                one line per attempt: stored, unchanged or failed
    raw/runs.jsonl                                 one line per job run
    tmp/                                           partial downloads, renamed into place when complete

`stamp` is the UTC fetch time without colons (Windows forbids them in names),
e.g. 20261018T110000Z. Nothing under raw/ is ever changed or deleted.

A new snapshot is stored only when the content differs from the latest one.
For most files the content is the bytes themselves. For web pages the caller
passes a hash of the extracted content instead, so that session tokens or
timestamps in the HTML don't count as a change.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from traceconomics import __version__

RAW = "raw"
INDEX = "index.jsonl"
RUNS = "runs.jsonl"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_name(part: str) -> str:
    bad = '<>:"/\\|?*'
    if not part or part in (".", "..") or any(c in bad for c in part):
        raise ValueError(f"Not a safe path part: {part!r}")
    return part


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".part")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _append_line(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


@dataclass(frozen=True)
class StoreResult:
    status: str  # "stored" or "unchanged"
    source: str
    dataset: str
    sha256: str
    path: Path | None  # payload path when stored


class Archive:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.raw = self.root / RAW
        self.tmp = self.root / "tmp"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self._snapshots: dict[tuple[str, str], list[dict]] = {}
        for rec in read_jsonl(self.raw / INDEX):
            if rec.get("status") == "stored":
                self._snapshots.setdefault((rec["source"], rec["dataset"]), []).append(rec)

    # -- reading ---------------------------------------------------------

    def datasets(self) -> list[tuple[str, str]]:
        """Every (source, dataset) with at least one stored snapshot."""
        return sorted(self._snapshots)

    def snapshots(self, source: str, dataset: str) -> list[dict]:
        """Stored snapshots of one dataset, oldest first by fetch time."""
        return sorted(self._snapshots.get((source, dataset), []), key=lambda r: r["retrieved_at"])

    def latest(self, source: str, dataset: str) -> dict | None:
        snaps = self.snapshots(source, dataset)
        return snaps[-1] if snaps else None

    def manifest(self, record: dict) -> dict:
        path = self.root / record["path"]
        return json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))

    def index(self) -> list[dict]:
        return read_jsonl(self.raw / INDEX)

    def runs(self) -> list[dict]:
        return read_jsonl(self.raw / RUNS)

    def stored_since(self, logged_after: str | None) -> list[dict]:
        """Index entries stored after a given log time (ISO, UTC), for backup lists."""
        return [
            r for r in self.index()
            if r.get("status") == "stored" and (logged_after is None or r["logged_at"] > logged_after)
        ]

    # -- writing ---------------------------------------------------------

    def new_tmp(self, suffix: str = "") -> Path:
        return self.tmp / f"{uuid.uuid4().hex}{suffix}.part"

    def store_file(
        self,
        source: str,
        dataset: str,
        tmp_file: Path,
        *,
        url: str | None,
        retrieved_at: datetime,
        ext: str = "",
        content_sha256: str | None = None,
        http: dict | None = None,
        kind: str = "fetched",
        dedupe: str = "latest",
        extra: dict | None = None,
        move: bool = True,
    ) -> StoreResult:
        """Store a complete file unless its content matches an existing snapshot.

        dedupe="latest" compares with the newest snapshot (normal fetches);
        dedupe="any" compares with every snapshot (back-filling older files).
        With move=False the file is copied and the original left in place.
        """
        source, dataset = _safe_name(source), _safe_name(dataset)
        sha = sha256_file(tmp_file)
        content = content_sha256 or sha
        snaps = self.snapshots(source, dataset)
        if dedupe == "latest":
            compare = snaps[-1:]
        elif dedupe == "any":
            compare = snaps
        else:
            raise ValueError(dedupe)
        if any(s.get("content_sha256", s["sha256"]) == content for s in compare):
            if move:
                tmp_file.unlink(missing_ok=True)
            self._log({
                "status": "unchanged", "source": source, "dataset": dataset, "url": url,
                "sha256": sha, "content_sha256": content, "retrieved_at": iso(retrieved_at),
            })
            return StoreResult("unchanged", source, dataset, sha, None)

        folder = self._new_folder(source, dataset, retrieved_at)
        payload = folder / f"payload{ext}"
        if move:
            os.replace(tmp_file, payload)
        else:
            part = payload.with_name(payload.name + ".part")
            shutil.copyfile(tmp_file, part)
            os.replace(part, payload)
        manifest = {
            "source": source,
            "dataset": dataset,
            "url": url,
            "retrieved_at": iso(retrieved_at),
            "sha256": sha,
            "content_sha256": content,
            "size": payload.stat().st_size,
            "kind": kind,
            "code_version": __version__,
        }
        if http:
            manifest["http"] = http
        if extra:
            manifest.update(extra)
        _write_atomic(folder / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        rec = self._log({
            "status": "stored", "source": source, "dataset": dataset, "url": url,
            "sha256": sha, "content_sha256": content, "retrieved_at": iso(retrieved_at),
            "path": payload.relative_to(self.root).as_posix(), "kind": kind,
        })
        self._snapshots.setdefault((source, dataset), []).append(rec)
        return StoreResult("stored", source, dataset, sha, payload)

    def store_bytes(self, source: str, dataset: str, data: bytes, **kw) -> StoreResult:
        tmp = self.new_tmp()
        _write_atomic(tmp, data)
        return self.store_file(source, dataset, tmp, **kw)

    def log_failure(self, source: str, dataset: str, url: str | None, error: str) -> None:
        self._log({"status": "failed", "source": source, "dataset": dataset, "url": url, "error": error})

    def log_unchanged_check(self, source: str, dataset: str, url: str | None, note: str) -> None:
        """Record that a cheap check (e.g. a "last updated" time) showed no change."""
        self._log({"status": "unchanged", "source": source, "dataset": dataset, "url": url, "note": note})

    def append_run(self, record: dict) -> None:
        _append_line(self.raw / RUNS, record)

    def clean_tmp(self) -> None:
        for p in self.tmp.glob("*.part"):
            p.unlink(missing_ok=True)

    # -- internals -------------------------------------------------------

    def _new_folder(self, source: str, dataset: str, ts: datetime) -> Path:
        base = self.raw / source / dataset
        name = stamp(ts)
        folder = base / name
        n = 2
        while folder.exists():
            folder = base / f"{name}-{n}"
            n += 1
        folder.mkdir(parents=True)
        return folder

    def _log(self, record: dict) -> dict:
        record = {"logged_at": iso(utc_now())} | record
        _append_line(self.raw / INDEX, record)
        return record
