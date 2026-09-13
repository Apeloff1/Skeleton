import json

import pytest

from core.content_store import ContentAddressedStore, ContentIntegrityError, ContentStoreError


def test_put_chunk_is_idempotent(tmp_path):
    store = ContentAddressedStore(tmp_path)
    first = store.put_chunk(b"abc")
    second = store.put_chunk(b"abc")
    assert first == second
    assert store.get_chunk(first) == b"abc"
    assert store.stats()["chunks"] == 1


def test_chunk_limit_is_enforced(tmp_path):
    store = ContentAddressedStore(tmp_path, chunk_max_bytes=3)
    with pytest.raises(ContentStoreError, match="exceeds"):
        store.put_chunk(b"four")


def test_put_bytes_chunks_and_reassembles(tmp_path):
    store = ContentAddressedStore(tmp_path, chunk_max_bytes=4)
    manifest = store.put_bytes("bundle", b"abcdefghij")
    assert len(manifest.chunks) == 3
    assert manifest.total_bytes == 10
    assert store.read_manifest(manifest) == b"abcdefghij"
    restored = store.load_manifest(manifest.id)
    assert restored == manifest


def test_empty_artifact_has_stable_chunk(tmp_path):
    store = ContentAddressedStore(tmp_path)
    manifest = store.put_bytes("empty", b"")
    assert len(manifest.chunks) == 1
    assert store.read_manifest(manifest) == b""


def test_unknown_chunk_fails(tmp_path):
    store = ContentAddressedStore(tmp_path)
    with pytest.raises(ContentStoreError, match="unknown chunk"):
        store.get_chunk("0" * 64)


def test_tampered_chunk_fails_closed(tmp_path):
    store = ContentAddressedStore(tmp_path)
    digest = store.put_chunk(b"trusted")
    store._chunk_path(digest).write_bytes(b"tampered")
    with pytest.raises(ContentIntegrityError, match="corrupt"):
        store.get_chunk(digest)


def test_manifest_with_unknown_chunk_is_rejected(tmp_path):
    store = ContentAddressedStore(tmp_path)
    with pytest.raises(ContentStoreError, match="unknown chunk"):
        store.pin_manifest("bad", ["f" * 64])


def test_corrupt_manifest_fails_closed(tmp_path):
    store = ContentAddressedStore(tmp_path)
    manifest = store.put_bytes("ok", b"payload")
    path = store.manifests_dir / f"{manifest.id}.json"
    path.write_text(json.dumps({"id": manifest.id}), encoding="utf-8")
    with pytest.raises(ContentIntegrityError, match="unreadable"):
        store.load_manifest(manifest.id)
