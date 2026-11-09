"""Fail-closed local GGUF artifact qualification.

This module verifies artifact custody only. It does not load model weights into
an inference backend or certify that token generation is available.
"""
from __future__ import annotations

import hashlib
import os
import stat
import struct
from pathlib import Path
from typing import Optional

from .fail_closed import guard_cas

MAX_GGUF_BYTES = 64 * 1024 ** 3
_GGUF_HEADER_BYTES = 24
_SUPPORTED_GGUF_VERSIONS = (2, 3)


class ModelLoader:
    def __init__(self, model_path: Optional[str] = None, *, expected_sha256: Optional[str] = None):
        self.model_path = Path(model_path) if model_path else None
        self.expected_sha256 = expected_sha256
        self.digest: Optional[str] = None
        self.loaded = False

    def load(self, cas: str) -> dict:
        guard_cas(cas)
        self.loaded = False
        self.digest = None
        if self.model_path is None:
            raise FileNotFoundError("GGUF model path is not configured")
        expected = self.expected_sha256
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("verified lowercase SHA-256 is required for GGUF qualification")
        # Qualification must never follow the final path component even on
        # platforms where O_NOFOLLOW does not exist: fail closed instead.
        if not hasattr(os, "O_NOFOLLOW"):
            raise OSError("secure GGUF no-follow open unsupported")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
        fd = os.open(self.model_path, flags)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or not _GGUF_HEADER_BYTES <= before.st_size <= MAX_GGUF_BYTES):
                raise ValueError("GGUF artifact must be bounded regular single-link file")
            path_before = os.lstat(self.model_path)
            if (not stat.S_ISREG(path_before.st_mode) or
                    (path_before.st_dev, path_before.st_ino) !=
                    (before.st_dev, before.st_ino)):
                raise ValueError("GGUF path changed during open")
            digest = hashlib.sha256()
            with os.fdopen(fd, "rb", closefd=False) as stream:
                header = stream.read(_GGUF_HEADER_BYTES)
                if len(header) != _GGUF_HEADER_BYTES or header[:4] != b"GGUF":
                    raise ValueError("artifact is not a complete GGUF header")
                version, tensors, metadata = struct.unpack_from("<IQQ", header, 4)
                if (version not in _SUPPORTED_GGUF_VERSIONS
                        or tensors == 0 or metadata == 0
                        or tensors > before.st_size // 8
                        or metadata > before.st_size // 8):
                    raise ValueError("unsupported or inconsistent GGUF header")
                digest.update(header)
                total = len(header)
                while True:
                    chunk = stream.read(min(1024 * 1024, MAX_GGUF_BYTES - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_GGUF_BYTES:
                        raise ValueError("GGUF artifact exceeded maximum byte budget")
                    digest.update(chunk)
            after = os.fstat(fd)
            path_after = os.lstat(self.model_path)
            fields = ("st_dev", "st_ino", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
            identity = lambda info: tuple(getattr(info, field) for field in fields)
            if (identity(before) != identity(after)
                    or identity(after) != identity(path_after)
                    or total != before.st_size):
                raise ValueError("GGUF artifact changed during verification")
            actual = digest.hexdigest()
            if actual != expected:
                raise ValueError("GGUF SHA-256 mismatch")
            self.digest = actual
            # Qualification is not a native model load. Keep loaded false.
            return {"status": "artifact_verified_only", "digest": actual, "bytes": after.st_size}
        finally:
            os.close(fd)

    def verify(self, expected: str) -> bool:
        return self.loaded and self.digest == expected
