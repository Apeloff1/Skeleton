"""Fail-closed GGUF artifact qualification; not an inference engine.

A qualified artifact is *not* a loaded model. Only the canonical provider
runtime may activate a verified backend and tokenizer under the sealed guard.
"""
from __future__ import annotations

import hashlib
import os
import stat
import struct
from pathlib import Path
from typing import Optional

from .fail_closed import guard_cas

_CHUNK = 1024 * 1024
_GGUF_MAGIC = b"GGUF"
_GGUF_HEADER_SIZE = 24
_SUPPORTED_GGUF_VERSIONS = frozenset({2, 3})


class ModelLoader:
    """Legacy artifact inspector; never simulates a successful model load."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = Path(model_path) if model_path else None
        self.digest: Optional[str] = None
        self.loaded = False

    def load(self, cas: str, *, expected_sha256: str | None = None,
             license_accepted: bool = False, max_bytes: int = 64 * 1024**3) -> dict:
        self.digest = None
        self.loaded = False
        guard_cas(cas)
        if not license_accepted:
            raise PermissionError("model license acceptance required")
        if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
                or any(c not in "0123456789abcdef" for c in expected_sha256)):
            raise ValueError("expected full SHA-256 digest required")
        if type(max_bytes) is not int or not _GGUF_HEADER_SIZE <= max_bytes <= 64 * 1024**3:
            raise ValueError("invalid model byte budget")
        if self.model_path is None:
            raise FileNotFoundError("GGUF model path is required")
        # Descriptor anchored and no-follow. Do not trust path.exists/read_bytes.
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if not hasattr(os, "O_NOFOLLOW"):
            raise OSError("secure model open is unsupported on this platform")
        flags |= os.O_NOFOLLOW
        fd = os.open(self.model_path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError("model must be a regular non-hardlinked file")
            if not _GGUF_HEADER_SIZE <= before.st_size <= max_bytes:
                raise ValueError("model size outside admitted budget")
            path_stat = os.lstat(self.model_path)
            if (path_stat.st_dev, path_stat.st_ino) != (before.st_dev, before.st_ino):
                raise OSError("model path changed during open")
            digest = hashlib.sha256()
            total = 0
            header = bytearray()
            while True:
                chunk = os.read(fd, min(_CHUNK, max_bytes - total + 1))
                if not chunk:
                    break
                if len(header) < _GGUF_HEADER_SIZE:
                    header.extend(chunk[:_GGUF_HEADER_SIZE - len(header)])
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("model exceeded byte budget")
                digest.update(chunk)
            after = os.fstat(fd)
            path_after = os.lstat(self.model_path)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                    before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns):
                raise OSError("model changed during verification")
            if (path_after.st_dev, path_after.st_ino) != (after.st_dev, after.st_ino):
                raise OSError("model path replaced during verification")
            if header[:4] != _GGUF_MAGIC:
                raise ValueError("not a GGUF artifact")
            version, tensors, metadata = struct.unpack_from("<IQQ", header, 4)
            if version not in _SUPPORTED_GGUF_VERSIONS or tensors == 0 or metadata == 0:
                raise ValueError("unsupported or empty GGUF header")
            if tensors > before.st_size // 8 or metadata > before.st_size // 8:
                raise ValueError("GGUF header counts exceed artifact bounds")
            if digest.hexdigest() != expected_sha256:
                raise ValueError("model SHA-256 mismatch")
            self.digest = expected_sha256
            # Deliberately not loaded: verification cannot claim native inference.
            return {"status": "artifact_verified_not_loaded", "digest": self.digest,
                    "bytes": total, "path": str(self.model_path)}
        finally:
            os.close(fd)

    def verify(self, expected: str) -> bool:
        return self.loaded and self.digest == expected
