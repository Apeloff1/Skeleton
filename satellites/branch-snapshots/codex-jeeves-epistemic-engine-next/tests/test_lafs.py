"""LAFS content-addressed chunk store — port of gameforge-rs lafs.rs."""

from __future__ import annotations

import hashlib

import pytest

from skeleton.forge.lafs import (
    CHUNK_CAP,
    CHUNK_MAX_BYTES,
    Chunk,
    Lafs,
    LafsError,
    Manifest,
)


@pytest.fixture()
def lafs() -> Lafs:
    return Lafs()


def test_put_chunk_returns_sha256(lafs: Lafs):
    data = b"hello labyrinth"
    digest = lafs.put_chunk(data)
    assert digest == hashlib.sha256(data).hexdigest()
    chunk = lafs.get_chunk(digest)
    assert isinstance(chunk, Chunk)
    assert chunk.bytes == data
    assert chunk.digest == digest


def test_put_chunk_idempotent(lafs: Lafs):
    data = b"same room twice"
    a = lafs.put_chunk(data)
    b = lafs.put_chunk(data)
    assert a == b
    assert lafs.stats()["chunks"] == 1


def test_put_chunk_rejects_oversize(lafs: Lafs):
    with pytest.raises(LafsError, match="1 MiB"):
        lafs.put_chunk(b"x" * (CHUNK_MAX_BYTES + 1))


def test_put_chunk_capacity(lafs: Lafs):
    """At CHUNK_CAP further distinct writes refuse (RS semantics)."""
    # Fill via tiny cap by driving internal store directly.
    for i in range(CHUNK_CAP):
        lafs.put_chunk(f"chunk-{i}".encode())
    assert lafs.stats()["chunks"] == CHUNK_CAP
    with pytest.raises(LafsError, match="capacity"):
        lafs.put_chunk(b"one-too-many")
    # Idempotent re-put of an existing digest still succeeds.
    first = hashlib.sha256(b"chunk-0").hexdigest()
    assert lafs.put_chunk(b"chunk-0") == first


def test_pin_manifest_and_read(lafs: Lafs):
    d1 = lafs.put_chunk(b"alpha")
    d2 = lafs.put_chunk(b"beta")
    m = lafs.pin_manifest("file.bin", [d1, d2])
    assert isinstance(m, Manifest)
    assert m.name == "file.bin"
    assert m.chunks == [d1, d2]
    assert m.total_bytes == 9
    assert lafs.read_manifest("file.bin") == b"alphabeta"


def test_pin_manifest_unknown_chunk_fail_closed(lafs: Lafs):
    with pytest.raises(LafsError, match="unknown chunk"):
        lafs.pin_manifest("ghost", ["0" * 64])


def test_read_manifest_missing_returns_none(lafs: Lafs):
    assert lafs.read_manifest("nope") is None


def test_read_manifest_verifies_digest(lafs: Lafs):
    digest = lafs.put_chunk(b"honest")
    lafs.pin_manifest("sealed", [digest])
    # Corrupt the room underneath the lock (test-only sabotage).
    with lafs._lock:
        corrupt = lafs._chunks[digest]
        lafs._chunks[digest] = Chunk(
            digest=digest, bytes=b"tampered", stored=corrupt.stored
        )
    assert lafs.read_manifest("sealed") is None


def test_manifests_and_stats(lafs: Lafs):
    d = lafs.put_chunk(b"x")
    lafs.pin_manifest("a", [d])
    lafs.pin_manifest("b", [d])
    names = {m.name for m in lafs.manifests()}
    assert names == {"a", "b"}
    stats = lafs.stats()
    assert stats["chunks"] == 1
    assert stats["bytes"] == 1
    assert stats["manifests"] == 2


def test_get_chunk_missing(lafs: Lafs):
    assert lafs.get_chunk("deadbeef" * 8) is None
