"""Which archived snapshots feed which store dataset, in the order they must be read."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from traceconomics.archive.store import Archive
from traceconomics.catalog import DatasetSpec


@dataclass(frozen=True)
class Snapshot:
    archive_dataset: str      # source/dataset in the archive, e.g. "elstat/doc-585819"
    path: Path                # the payload
    sha256: str
    retrieved_at: str         # ISO UTC, as in the archive index
    manifest: dict


def snapshots(archive: Archive, spec: DatasetSpec) -> dict[str, list[Snapshot]]:
    """archive dataset -> its snapshots, oldest first. Each archive dataset is read in order
    and compared only with itself."""
    out: dict[str, list[Snapshot]] = {}
    for source, dataset in archive.datasets():
        for rec in archive.snapshots(source, dataset):
            manifest = archive.manifest(rec)
            if not spec.feeds(source, dataset, manifest.get("original_name")):
                continue
            out.setdefault(f"{source}/{dataset}", []).append(Snapshot(
                archive_dataset=f"{source}/{dataset}", path=archive.root / rec["path"],
                sha256=rec["sha256"], retrieved_at=rec["retrieved_at"], manifest=manifest))
    return out


def label_files(archive: Archive, spec: DatasetSpec) -> list[Path]:
    """The newest snapshot of every archived file read for labels, oldest first."""
    if spec.label_files is None:
        return []
    found = []
    for source, dataset in archive.datasets():
        if source != spec.source:
            continue
        rec = archive.latest(source, dataset)
        name = archive.manifest(rec).get("original_name") or ""
        if spec.label_files.search(name):
            found.append((rec["retrieved_at"], archive.root / rec["path"]))
    return [p for _, p in sorted(found)]
