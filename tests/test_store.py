import json
from datetime import UTC, datetime

from traceconomics.archive.store import Archive, sha256_text

T1 = datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC)
T2 = datetime(2026, 10, 19, 11, 0, 0, tzinfo=UTC)


def test_store_then_unchanged(tmp_path):
    a = Archive(tmp_path)
    r1 = a.store_bytes("src", "ds", b"hello", url="u", retrieved_at=T1, ext=".txt")
    r2 = a.store_bytes("src", "ds", b"hello", url="u", retrieved_at=T2, ext=".txt")
    assert (r1.status, r2.status) == ("stored", "unchanged")
    assert r1.path.read_bytes() == b"hello"
    assert r1.path.parent.name == "20261018T110000Z"  # no colons
    manifest = json.loads((r1.path.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["url"] == "u" and manifest["size"] == 5
    statuses = [r["status"] for r in a.index()]
    assert statuses == ["stored", "unchanged"]
    assert not list(a.tmp.iterdir())  # temporary files cleaned up


def test_change_is_stored_and_index_survives_reload(tmp_path):
    a = Archive(tmp_path)
    a.store_bytes("src", "ds", b"v1", url=None, retrieved_at=T1)
    a.store_bytes("src", "ds", b"v2", url=None, retrieved_at=T2)
    again = Archive(tmp_path)
    assert len(again.snapshots("src", "ds")) == 2
    assert again.latest("src", "ds")["retrieved_at"] == "2026-10-19T11:00:00Z"


def test_content_hash_ignores_noise(tmp_path):
    a = Archive(tmp_path)
    key = sha256_text("same visible text")
    r1 = a.store_bytes("src", "page", b"<html>session=1</html>", url=None, retrieved_at=T1, content_sha256=key)
    r2 = a.store_bytes("src", "page", b"<html>session=2</html>", url=None, retrieved_at=T2, content_sha256=key)
    assert (r1.status, r2.status) == ("stored", "unchanged")


def test_same_second_gets_a_new_folder(tmp_path):
    a = Archive(tmp_path)
    r1 = a.store_bytes("src", "ds", b"a", url=None, retrieved_at=T1)
    r2 = a.store_bytes("src", "ds", b"b", url=None, retrieved_at=T1)
    assert r1.path.parent != r2.path.parent


def test_dedupe_any_for_backfill(tmp_path):
    a = Archive(tmp_path)
    a.store_bytes("src", "ds", b"old", url=None, retrieved_at=T1)
    a.store_bytes("src", "ds", b"new", url=None, retrieved_at=T2)
    r = a.store_bytes("src", "ds", b"old", url=None, retrieved_at=T2, dedupe="any")
    assert r.status == "unchanged"


def test_unsafe_names_rejected(tmp_path):
    import pytest

    a = Archive(tmp_path)
    with pytest.raises(ValueError):
        a.store_bytes("src", "../x", b"a", url=None, retrieved_at=T1)


def test_stored_since(tmp_path):
    a = Archive(tmp_path)
    a.store_bytes("src", "ds", b"a", url=None, retrieved_at=T1)
    assert len(a.stored_since(None)) == 1
    assert a.stored_since("9999-01-01T00:00:00Z") == []
