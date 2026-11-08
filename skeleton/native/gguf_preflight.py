"""Fail-closed, bounded GGUF header preflight; not model activation or rights approval.

This checks the file identity and basic GGUF framing before an independently
authorized loader opens the weights. It does not attest a tokenizer, license,
tensor contents, or inference capability.
"""
from __future__ import annotations

import hashlib
import os
import stat
import struct
from dataclasses import dataclass
from pathlib import Path


class GGUFPreflightError(ValueError):
    """Model bytes cannot be admitted for further qualification."""


@dataclass(frozen=True)
class GGUFHeader:
    version: int
    tensor_count: int
    metadata_count: int
    file_size: int
    sha256: str


def inspect_gguf(
    path: str | Path,
    *,
    expected_sha256: str,
    max_bytes: int = 128 * 1024 * 1024 * 1024,
    max_tensors: int = 1_000_000,
    max_metadata: int = 1_000_000,
) -> GGUFHeader:
    """Read a stable regular file through a no-follow descriptor and hash all bytes.

    The caller must independently validate rights, tokenizer and trusted model
    binding; this function never activates a model or follows a symbolic link.
    """
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or any(
        ch not in "0123456789abcdef" for ch in expected_sha256
    ):
        raise GGUFPreflightError("expected_sha256 must be lowercase SHA-256")
    for value in (max_bytes, max_tensors, max_metadata):
        if type(value) is not int or value <= 0:
            raise GGUFPreflightError("limits must be positive integers")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if not hasattr(os, "O_NOFOLLOW"):
        raise GGUFPreflightError("no-follow file open unavailable")
    flags |= os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(os.fspath(path), flags)
    except OSError as exc:
        raise GGUFPreflightError("model file unavailable or unsafe") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size < 24 or before.st_size > max_bytes:
            raise GGUFPreflightError("model file size/type rejected")
        header = os.read(fd, 24)
        if len(header) != 24 or header[:4] != b"GGUF":
            raise GGUFPreflightError("not a GGUF model")
        version = struct.unpack_from("<I", header, 4)[0]
        if version not in (2, 3):
            raise GGUFPreflightError("unsupported GGUF version")
        tensors, metadata = struct.unpack_from("<QQ", header, 8)
        if tensors == 0 or tensors > max_tensors or metadata > max_metadata:
            raise GGUFPreflightError("GGUF counts exceed bounds")
        digest = hashlib.sha256()
        digest.update(header)
        total = len(header)
        while True:
            block = os.read(fd, min(1024 * 1024, max_bytes - total + 1))
            if not block:
                break
            total += len(block)
            if total > max_bytes:
                raise GGUFPreflightError("model exceeds byte budget")
            digest.update(block)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or total != before.st_size:
            raise GGUFPreflightError("model changed during inspection")
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise GGUFPreflightError("model SHA-256 mismatch")
        return GGUFHeader(version, tensors, metadata, total, actual)
    finally:
        os.close(fd)
