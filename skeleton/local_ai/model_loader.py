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
_MIN_GGUF_BYTES = 25
_SUPPORTED_GGUF_VERSIONS = frozenset({2, 3})


def _open_model(path: Path) -> tuple[int, int, Path]:
    """Refuse symlinked parents and pin the full model ancestry by descriptor."""
    if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
            or os.open not in os.supports_dir_fd
            or os.stat not in os.supports_dir_fd):
        raise OSError("secure GGUF descriptor-relative open is unavailable")
    if ".." in path.parts or path.name in ("", ".", ".."):
        raise ValueError("GGUF path may not traverse parent components")
    absolute = path.absolute()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    dfd = os.open("/", flags)
    try:
        for component in absolute.parts[1:-1]:
            child = os.open(component, flags, dir_fd=dfd)
            os.close(dfd)
            dfd = child
        fd = os.open(
            absolute.name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=dfd,
        )
        return dfd, fd, absolute
    except BaseException:
        os.close(dfd)
        raise


class ModelLoader:
    """Legacy artifact inspector; never simulates a successful model load."""

    def __init__(self, model_path: Optional[str] = None, *,
                 expected_sha256: Optional[str] = None):
        self.model_path = Path(model_path) if model_path else None
        self.expected_sha256 = expected_sha256
        self.digest: Optional[str] = None
        self.loaded = False

    def load(self, cas: str, *, expected_sha256: str | None = None,
             license_accepted: bool = False, max_bytes: int = 64 * 1024**3) -> dict:
        self.digest = None
        self.loaded = False
        guard_cas(cas)
        if license_accepted is not True:
            raise PermissionError("model license acceptance required")
        expected = expected_sha256 if expected_sha256 is not None else self.expected_sha256
        if (not isinstance(expected, str) or len(expected) != 64
                or any(c not in "0123456789abcdef" for c in expected)):
            raise ValueError("expected full SHA-256 digest required")
        if type(max_bytes) is not int or not _MIN_GGUF_BYTES <= max_bytes <= 64 * 1024**3:
            raise ValueError("invalid model byte budget")
        if self.model_path is None:
            raise FileNotFoundError("GGUF model path is required")
        dfd, fd, absolute = _open_model(self.model_path)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError("model must be a regular non-hardlinked file")
            if not _MIN_GGUF_BYTES <= before.st_size <= max_bytes:
                raise ValueError("model size outside admitted budget")
            path_stat = os.stat(absolute.name, dir_fd=dfd, follow_symlinks=False)
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
            path_after = os.stat(absolute.name, dir_fd=dfd, follow_symlinks=False)
            # The file descriptor pins the opened directory; also reject
            # a pathname parent replaced during source verification.
            parent_after = os.stat(absolute.parent, follow_symlinks=False)
            parent = os.fstat(dfd)
            if (parent_after.st_dev, parent_after.st_ino) != (parent.st_dev, parent.st_ino):
                raise OSError("model parent changed during verification")
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
            if digest.hexdigest() != expected:
                raise ValueError("model SHA-256 mismatch")
            self.digest = expected
            # Deliberately not loaded: verification cannot claim native inference.
            return {"status": "artifact_verified_only", "digest": self.digest,
                    "bytes": total}
        finally:
            os.close(fd)
            os.close(dfd)

    def verify(self, expected: str) -> bool:
        return self.loaded and self.digest == expected
