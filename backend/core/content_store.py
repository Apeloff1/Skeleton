"""Content-addressed artifact storage mined from gameforge-rs LAFS.

Unlike the Rust prototype's in-memory chunk map, this implementation is disk-backed,
uses atomic writes, verifies every digest on read, and stores manifests separately.
It is intended for generated source bundles, build inputs, exports, and provenance
objects that must be immutable once addressed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import uuid


DEFAULT_CHUNK_MAX_BYTES = 1 << 20


class ContentStoreError(RuntimeError):
    pass


class ContentIntegrityError(ContentStoreError):
    pass


@dataclass(frozen=True, slots=True)
class Manifest:
    id: str
    name: str
    chunks: tuple[str, ...]
    total_bytes: int
    created_at: str


class ContentAddressedStore:
    def __init__(self, root: str | os.PathLike[str], *, chunk_max_bytes: int = DEFAULT_CHUNK_MAX_BYTES) -> None:
        if chunk_max_bytes <= 0:
            raise ValueError("chunk_max_bytes must be positive")
        self.root = Path(root)
        self.chunks_dir = self.root / "chunks"
        self.manifests_dir = self.root / "manifests"
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_max_bytes = chunk_max_bytes
        self._lock = threading.RLock()

    @staticmethod
    def digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _chunk_path(self, digest: str) -> Path:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid sha256 digest")
        return self.chunks_dir / digest[:2] / digest[2:]

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def put_chunk(self, data: bytes) -> str:
        data = bytes(data)
        if len(data) > self.chunk_max_bytes:
            raise ContentStoreError(f"chunk exceeds {self.chunk_max_bytes} bytes")
        digest = self.digest(data)
        path = self._chunk_path(digest)
        with self._lock:
            if path.exists():
                existing = path.read_bytes()
                if self.digest(existing) != digest:
                    raise ContentIntegrityError(f"stored chunk corrupt: {digest}")
                return digest
            self._atomic_write(path, data)
        return digest

    def get_chunk(self, digest: str) -> bytes:
        path = self._chunk_path(digest)
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise ContentStoreError(f"unknown chunk {digest}") from exc
        if self.digest(data) != digest:
            raise ContentIntegrityError(f"stored chunk corrupt: {digest}")
        return data

    def put_bytes(self, name: str, data: bytes) -> Manifest:
        if not name.strip():
            raise ValueError("manifest name is required")
        data = bytes(data)
        digests = tuple(
            self.put_chunk(data[offset : offset + self.chunk_max_bytes])
            for offset in range(0, len(data), self.chunk_max_bytes)
        )
        if not digests:
            digests = (self.put_chunk(b""),)
        return self.pin_manifest(name, digests)

    def pin_manifest(self, name: str, digests: tuple[str, ...] | list[str]) -> Manifest:
        normalized = tuple(digests)
        total = 0
        for digest in normalized:
            total += len(self.get_chunk(digest))
        manifest = Manifest(
            id=uuid.uuid4().hex,
            name=name.strip(),
            chunks=normalized,
            total_bytes=total,
            created_at=datetime.now(UTC).isoformat(),
        )
        payload = json.dumps(asdict(manifest), sort_keys=True, separators=(",", ":")).encode()
        path = self.manifests_dir / f"{manifest.id}.json"
        with self._lock:
            self._atomic_write(path, payload)
        return manifest

    def read_manifest(self, manifest: Manifest) -> bytes:
        out = bytearray()
        for digest in manifest.chunks:
            out.extend(self.get_chunk(digest))
        if len(out) != manifest.total_bytes:
            raise ContentIntegrityError("manifest byte count mismatch")
        return bytes(out)

    def load_manifest(self, manifest_id: str) -> Manifest:
        path = self.manifests_dir / f"{manifest_id}.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["chunks"] = tuple(raw["chunks"])
            return Manifest(**raw)
        except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ContentIntegrityError(f"manifest unreadable: {manifest_id}") from exc

    def stats(self) -> dict[str, int]:
        chunk_files = [p for p in self.chunks_dir.rglob("*") if p.is_file()]
        manifest_files = [p for p in self.manifests_dir.glob("*.json") if p.is_file()]
        return {
            "chunks": len(chunk_files),
            "bytes": sum(p.stat().st_size for p in chunk_files),
            "manifests": len(manifest_files),
        }
