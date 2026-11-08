"""Fail-closed GGUF artifact qualification, not a model execution backend.

This module verifies a caller-pinned artifact before passing it to the canonical
provider runtime. A verified file is never reported as an activated model.
"""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Optional

from .fail_closed import guard_cas

_GGUF_MAGIC = b"GGUF"
_CHUNK = 1024 * 1024


class ModelLoader:
    def __init__(
        self,
        model_path: Optional[str] = None,
        *,
        expected_sha256: Optional[str] = None,
        license_accepted: bool = False,
        max_bytes: int = 64 * 1024**3,
    ):
        self.model_path = Path(model_path) if model_path else None
        self.expected_sha256 = expected_sha256
        self.license_accepted = license_accepted
        self.max_bytes = max_bytes
        self.digest: Optional[str] = None
        self.loaded = False

    def load(self, cas: str) -> dict:
        guard_cas(cas)
        self.loaded = False
        self.digest = None
        if not self.model_path:
            raise FileNotFoundError("GGUF model path is required")
        if not self.license_accepted:
            raise PermissionError("model license acceptance is required")
        expected = self.expected_sha256
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("pinned lowercase SHA-256 is required")
        if isinstance(self.max_bytes, bool) or not isinstance(self.max_bytes, int) or self.max_bytes < 8:
            raise ValueError("invalid model size bound")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(self.model_path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size < 8 or before.st_size > self.max_bytes:
                raise ValueError("GGUF model size/type rejected")
            with os.fdopen(fd, "rb", closefd=False) as source:
                header = source.read(8)
                if header[:4] != _GGUF_MAGIC or int.from_bytes(header[4:], "little") not in (2, 3):
                    raise ValueError("unsupported GGUF header/version")
                sha = hashlib.sha256()
                sha.update(header)
                count = len(header)
                while True:
                    chunk = source.read(min(_CHUNK, self.max_bytes + 1 - count))
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > self.max_bytes:
                        raise ValueError("GGUF exceeds size bound")
                    sha.update(chunk)
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            ) or count != before.st_size:
                raise RuntimeError("GGUF changed during qualification")
            digest = sha.hexdigest()
            if digest != expected:
                raise ValueError("GGUF SHA-256 mismatch")
            self.digest = digest
            return {"status": "artifact_verified_not_loaded", "digest": digest, "bytes": count}
        finally:
            os.close(fd)

    def verify(self, expected: str) -> bool:
        return self.loaded and self.digest == expected
