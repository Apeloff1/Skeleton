"""LAFS — Labyrinthine Append-only File Store.

Port of gameforge-rs ``crates/gf-gameforge/src/lafs.rs``. Content-addressed
chunks under manifests. A chunk is written once, addressed by its SHA-256
digest (F1 fix — a content-addressed store with a non-cryptographic address
is corruptible by anyone who can write two chunks), and never mutated. The
labyrinth has no erasers, only new rooms. Manifests pin chunk order; every
file in the empire has a provenance chain back through the quorum gate.

This is the forge-path chunk store (hex address = SHA-256), **not** the
Bayesian Lever Arch knowledge ledger under ``backend/gameforge/lafs/``.

Optional light integration: callers that already journal via
``skeleton.forge.outbox.MaterialiseOutbox`` may store blueprint payloads
through ``Lafs.put_chunk`` / ``pin_manifest`` and record digests on the
intent document — extend-only; outbox itself is unchanged.
"""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from skeleton.kernel.errors import SkeletonError

CHUNK_CAP = 16384
CHUNK_MAX_BYTES = 1 << 20  # 1 MiB


class LafsError(SkeletonError):
    """LAFS refuse — oversize chunk, capacity, unknown digest, corruption."""

    code = "FORGE.LAFS"
    http_status = 400


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Chunk:
    """One immutable content-addressed blob."""

    digest: str
    bytes: bytes
    stored: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "size": len(self.bytes),
            "stored": self.stored,
        }


@dataclass
class Manifest:
    """Ordered pin of chunk digests assembling one logical file."""

    name: str
    chunks: list[str]
    total_bytes: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "chunks": list(self.chunks),
            "total_bytes": self.total_bytes,
            "created": self.created,
        }


class Lafs:
    """In-process content-addressed chunk store + manifest pins.

    Thread-safe via a single RLock (mirrors the RS RwLock covering chunk /
    manifesto mutation so observers never see a half-written room).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._chunks: dict[str, Chunk] = {}
        self._manifests: dict[str, Manifest] = {}

    def put_chunk(self, data: bytes) -> str:
        """Store a chunk. Idempotent: same bytes, same room. Returns digest."""
        if len(data) > CHUNK_MAX_BYTES:
            raise LafsError("chunk exceeds 1 MiB")
        digest = _sha256_hex(data)
        with self._lock:
            if digest in self._chunks:
                return digest  # already in the labyrinth
            if len(self._chunks) >= CHUNK_CAP:
                raise LafsError("chunk store at capacity — compact before writing")
            self._chunks[digest] = Chunk(digest=digest, bytes=bytes(data))
            return digest

    def get_chunk(self, digest: str) -> Chunk | None:
        with self._lock:
            chunk = self._chunks.get(digest)
            if chunk is None:
                return None
            return Chunk(digest=chunk.digest, bytes=chunk.bytes, stored=chunk.stored)

    def pin_manifest(self, name: str, digests: list[str]) -> Manifest:
        """Pin a manifest. Every chunk must already exist."""
        with self._lock:
            total = 0
            for d in digests:
                chunk = self._chunks.get(d)
                if chunk is None:
                    raise LafsError(f"unknown chunk {d}")
                total += len(chunk.bytes)
            manifest = Manifest(
                name=name,
                chunks=list(digests),
                total_bytes=total,
            )
            self._manifests[name] = manifest
            return Manifest(
                name=manifest.name,
                chunks=list(manifest.chunks),
                total_bytes=manifest.total_bytes,
                id=manifest.id,
                created=manifest.created,
            )

    def read_manifest(self, name: str) -> bytes | None:
        """Reassemble a file through its manifest, verifying every digest."""
        with self._lock:
            manifest = self._manifests.get(name)
            if manifest is None:
                return None
            out = bytearray()
            for d in manifest.chunks:
                chunk = self._chunks.get(d)
                if chunk is None:
                    return None
                if _sha256_hex(chunk.bytes) != d:
                    return None  # corruption — the room's contents changed
                out.extend(chunk.bytes)
            return bytes(out)

    def manifests(self) -> list[Manifest]:
        with self._lock:
            return [
                Manifest(
                    name=m.name,
                    chunks=list(m.chunks),
                    total_bytes=m.total_bytes,
                    id=m.id,
                    created=m.created,
                )
                for m in self._manifests.values()
            ]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            byte_sum = sum(len(c.bytes) for c in self._chunks.values())
            return {
                "chunks": len(self._chunks),
                "bytes": byte_sum,
                "manifests": len(self._manifests),
            }
