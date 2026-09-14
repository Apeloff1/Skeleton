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
    assert len(manifest.id) == 64
    assert len(manifest.content_sha256) == 64
    assert store.read_manifest(manifest) == b"abcdefghij"
    restored = store.load_manifest(manifest.id)
    assert restored == manifest


def test_identical_artifact_manifest_is_content_addressed_and_idempotent(tmp_path):
    store = ContentAddressedStore(tmp_path, chunk_max_bytes=4)
    first = store.put_bytes("bundle", b"abcdefgh")
    second = store.put_bytes("bundle", b"abcdefgh")
    assert second == first
    assert store.stats()["manifests"] == 1


def test_manifest_name_participates_in_identity(tmp_path):
    store = ContentAddressedStore(tmp_path)
    first = store.put_bytes("alpha", b"same")
    second = store.put_bytes("beta", b"same")
    assert first.content_sha256 == second.content_sha256
    assert first.id != second.id


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


def test_manifest_envelope_tamper_fails_closed(tmp_path):
    store = ContentAddressedStore(tmp_path)
    manifest = store.put_bytes("ok", b"payload")
    path = store.manifests_dir / f"{manifest.id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["manifest"]["name"] = "evil"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ContentIntegrityError, match="checksum mismatch"):
        store.load_manifest(manifest.id)


def test_manifest_identity_tamper_fails_even_with_recomputed_envelope(tmp_path):
    store = ContentAddressedStore(tmp_path)
    manifest = store.put_bytes("ok", b"payload")
    path = store.manifests_dir / f"{manifest.id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["manifest"]["total_bytes"] = 99
    raw["sha256"] = store.digest(store._canonical(raw["payload"]))
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ContentIntegrityError, match="identity checksum mismatch"):
        store.load_manifest(manifest.id)


def test_read_verifies_assembled_content_digest(tmp_path):
    store = ContentAddressedStore(tmp_path)
    manifest = store.put_bytes("ok", b"payload")
    forged = type(manifest)(
        id=manifest.id,
        name=manifest.name,
        chunks=manifest.chunks,
        total_bytes=manifest.total_bytes,
        created_at=manifest.created_at,
        content_sha256="0" * 64,
    )
    with pytest.raises(ContentIntegrityError):
        store.read_manifest(forged)


def test_legacy_uuid_manifest_is_read_compatible(tmp_path):
    store = ContentAddressedStore(tmp_path)
    chunk = store.put_chunk(b"legacy")
    legacy_id = "a" * 32
    path = store.manifests_dir / f"{legacy_id}.json"
    path.write_text(json.dumps({
        "id": legacy_id,
        "name": "legacy",
        "chunks": [chunk],
        "total_bytes": 6,
        "created_at": "2026-01-01T00:00:00+00:00",
    }), encoding="utf-8")
    manifest = store.load_manifest(legacy_id)
    assert manifest.id == legacy_id
    assert manifest.content_sha256 == store.digest(b"legacy")
    assert store.read_manifest(manifest) == b"legacy"


def test_invalid_manifest_id_is_rejected_without_path_traversal(tmp_path):
    store = ContentAddressedStore(tmp_path)
    with pytest.raises(ContentIntegrityError, match="invalid"):
        store.load_manifest("../../escape")
