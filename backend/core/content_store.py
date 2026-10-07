"""Disk-backed content-addressed artifact storage.

Chunks are addressed by SHA-256. New manifests are also content-addressed and
wrapped in a versioned checksum envelope, while legacy UUID manifests remain
readable for restart compatibility. Reads verify both chunk digests and the
assembled artifact digest.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any


DEFAULT_CHUNK_MAX_BYTES = 1 << 20
MANIFEST_VERSION = 2


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
    content_sha256: str


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

    @staticmethod
    def _canonical(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _valid_digest(value: str) -> bool:
        return len(value) == 64 and all(c in "0123456789abcdef" for c in value)

    def _chunk_path(self, digest: str) -> Path:
        if not self._valid_digest(digest):
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
                if not hmac.compare_digest(self.digest(existing), digest):
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
        if not hmac.compare_digest(self.digest(data), digest):
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
        return self.pin_manifest(name, digests, content_sha256=self.digest(data))

    @classmethod
    def _manifest_identity(cls, *, name: str, chunks: tuple[str, ...], total_bytes: int, content_sha256: str) -> str:
        identity = {
            "name": name,
            "chunks": list(chunks),
            "total_bytes": total_bytes,
            "content_sha256": content_sha256,
        }
        return hashlib.sha256(cls._canonical(identity)).hexdigest()

    def pin_manifest(
        self,
        name: str,
        digests: tuple[str, ...] | list[str],
        *,
        content_sha256: str | None = None,
    ) -> Manifest:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("manifest name is required")
        normalized = tuple(digests)
        if not normalized:
            raise ValueError("manifest requires at least one chunk")
        assembled = bytearray()
        for digest in normalized:
            assembled.extend(self.get_chunk(digest))
        total = len(assembled)
        calculated_content_digest = self.digest(bytes(assembled))
        if content_sha256 is not None and not hmac.compare_digest(content_sha256, calculated_content_digest):
            raise ContentIntegrityError("provided artifact digest does not match chunks")
        content_digest = content_sha256 or calculated_content_digest
        manifest_id = self._manifest_identity(
            name=clean_name,
            chunks=normalized,
            total_bytes=total,
            content_sha256=content_digest,
        )
        path = self.manifests_dir / f"{manifest_id}.json"
        with self._lock:
            if path.exists():
                existing = self.load_manifest(manifest_id)
                if (
                    existing.name != clean_name
                    or existing.chunks != normalized
                    or existing.total_bytes != total
                    or not hmac.compare_digest(existing.content_sha256, content_digest)
                ):
                    raise ContentIntegrityError("content-addressed manifest collision")
                return existing
            manifest = Manifest(
                id=manifest_id,
                name=clean_name,
                chunks=normalized,
                total_bytes=total,
                created_at=datetime.now(UTC).isoformat(),
                content_sha256=content_digest,
            )
            manifest_payload = asdict(manifest)
            envelope_payload = {"version": MANIFEST_VERSION, "manifest": manifest_payload}
            envelope = {"payload": envelope_payload, "sha256": self.digest(self._canonical(envelope_payload))}
            self._atomic_write(path, self._canonical(envelope))
        return manifest

    def _verify_manifest(self, manifest: Manifest, *, requested_id: str | None = None) -> None:
        if requested_id is not None and manifest.id != requested_id:
            raise ContentIntegrityError("manifest id mismatch")
        if not manifest.name.strip() or manifest.total_bytes < 0 or not manifest.chunks:
            raise ContentIntegrityError("manifest metadata is invalid")
        if not self._valid_digest(manifest.content_sha256):
            raise ContentIntegrityError("manifest content digest is invalid")
        for digest in manifest.chunks:
            if not self._valid_digest(digest):
                raise ContentIntegrityError("manifest contains invalid chunk digest")
        if len(manifest.id) == 64:
            expected_id = self._manifest_identity(
                name=manifest.name,
                chunks=manifest.chunks,
                total_bytes=manifest.total_bytes,
                content_sha256=manifest.content_sha256,
            )
            if not hmac.compare_digest(expected_id, manifest.id):
                raise ContentIntegrityError("manifest identity checksum mismatch")

    def read_manifest(self, manifest: Manifest) -> bytes:
        self._verify_manifest(manifest)
        out = bytearray()
        for digest in manifest.chunks:
            out.extend(self.get_chunk(digest))
        data = bytes(out)
        if len(data) != manifest.total_bytes:
            raise ContentIntegrityError("manifest byte count mismatch")
        if not hmac.compare_digest(self.digest(data), manifest.content_sha256):
            raise ContentIntegrityError("artifact content digest mismatch")
        return data

    def load_manifest(self, manifest_id: str) -> Manifest:
        if not manifest_id or any(c not in "0123456789abcdef" for c in manifest_id.lower()) or len(manifest_id) not in {32, 64}:
            raise ContentIntegrityError("manifest id is invalid")
        path = self.manifests_dir / f"{manifest_id}.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            raise ContentIntegrityError(f"manifest unreadable: {manifest_id}") from exc

        try:
            if isinstance(raw, dict) and "payload" in raw:
                payload = raw["payload"]
                digest = raw["sha256"]
                if not isinstance(payload, dict) or payload.get("version") != MANIFEST_VERSION or not isinstance(digest, str):
                    raise ContentIntegrityError("manifest envelope is malformed")
                expected = self.digest(self._canonical(payload))
                if not hmac.compare_digest(expected, digest):
                    raise ContentIntegrityError("manifest envelope checksum mismatch")
                body = dict(payload["manifest"])
                body["chunks"] = tuple(body["chunks"])
                manifest = Manifest(**body)
            else:
                # Legacy v1: raw UUID manifest without an envelope or artifact digest.
                body = dict(raw)
                chunks = tuple(body["chunks"])
                data = b"".join(self.get_chunk(digest) for digest in chunks)
                manifest = Manifest(
                    id=str(body["id"]),
                    name=str(body["name"]),
                    chunks=chunks,
                    total_bytes=int(body["total_bytes"]),
                    created_at=str(body["created_at"]),
                    content_sha256=self.digest(data),
                )
        except ContentIntegrityError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ContentIntegrityError(f"manifest unreadable: {manifest_id}") from exc

        self._verify_manifest(manifest, requested_id=manifest_id)
        return manifest

    def stats(self) -> dict[str, int]:
        chunk_files = [p for p in self.chunks_dir.rglob("*") if p.is_file()]
        manifest_files = [p for p in self.manifests_dir.glob("*.json") if p.is_file()]
        return {
            "chunks": len(chunk_files),
            "bytes": sum(p.stat().st_size for p in chunk_files),
            "manifests": len(manifest_files),
        }
