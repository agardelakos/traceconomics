"""Copy new archive files to private cloud storage, leaving the microdata out.

The archive is the record: every published value traces back to a file in it. This keeps a
second copy, off the machine, of everything under `raw/` except the datasets listed as
local-only, which must never be copied to cloud storage. Each file goes up once; a ledger next to
the archive remembers what was sent, by checksum, so a changed index is sent again.

The address is a pre-authenticated upload URL for one bucket (objects are named by their path
under the archive). It is a secret, so it comes only from the environment.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from traceconomics.archive.local_only import check, is_local_only
from traceconomics.archive.store import sha256_file

URL_ENV = "TRACECONOMICS_BACKUP_URL"
LEDGER = "state/backup-synced.json"


def _dataset_of(rel: Path) -> tuple[str, str] | None:
    """(source, dataset) for a file under raw/<source>/<dataset>/..., else None (e.g. the index)."""
    parts = rel.parts
    return (parts[1], parts[2]) if len(parts) >= 4 and parts[0] == "raw" else None


def plan(root: Path) -> list[tuple[str, str]]:
    """The files to send: (path under the archive, sha256), new or changed since the last sync."""
    sent = _load_ledger(root)
    out = []
    for path in sorted((root / "raw").rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        ds = _dataset_of(rel)
        if ds and is_local_only(*ds):
            continue
        name = rel.as_posix()
        digest = sha256_file(path)
        if sent.get(name) != digest:
            out.append((name, digest))
    # A second, independent guard: nothing local-only may be in the list, however it got there.
    check(ds for name, _ in out if (ds := _dataset_of(Path(name))))
    return out


def sync(root: Path, *, url: str | None = None, timeout: float = 120.0) -> dict:
    """Send what `plan` lists. Returns counts; stops at the first failed upload."""
    url = url or os.environ.get(URL_ENV)
    if not url:
        return {"result": "off"}
    todo = plan(root)
    sent = _load_ledger(root)
    done = 0
    for name, digest in todo:
        target = url.rstrip("/") + "/" + urllib.parse.quote(name)
        req = urllib.request.Request(target, data=(root / name).read_bytes(), method="PUT",
                                     headers={"Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read()
        except (urllib.error.URLError, OSError) as exc:
            _save_ledger(root, sent)
            return {"result": "failed", "sent": done, "left": len(todo) - done, "error": f"{name}: {exc}"}
        sent[name] = digest
        done += 1
    _save_ledger(root, sent)
    return {"result": "ok", "sent": done}


def _load_ledger(root: Path) -> dict[str, str]:
    path = root / LEDGER
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _save_ledger(root: Path, sent: dict[str, str]) -> None:
    path = root / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(sent, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
