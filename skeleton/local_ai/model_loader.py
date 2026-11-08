"""Fail-closed local GGUF artifact qualification.

This module verifies artifact custody only. It does not load model weights into
an inference backend or certify that token generation is available.
"""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Optional

from .fail_closed import guard_cas


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
        # Reject symlinks and changes of the final component; do not follow
        # the path after opening the descriptor.
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.model_path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size < 8:
                raise ValueError("GGUF artifact must be a nonempty regular file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                if stream.read(4) != b"GGUF":
                    raise ValueError("artifact is not GGUF")
                stream.seek(0)
                digest = hashlib.sha256()
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            ):
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
