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


class ModelLoader:
    """Legacy artifact inspector; never simulates a successful model load."""

    def __init__(self, model_path: Optional[str] = None, *, expected_sha256: Optional[str] = None):
        self.model_path = Path(model_path) if model_path else None
        self.expected_sha256 = expected_sha256
        self.digest: Optional[str] = None
        self.loaded = False

    def load(self, cas: str, *, expected_sha256: str | None = None,
             license_accepted: bool = False, max_bytes: int = 64 * 1024**3) -> dict:
        self.digest = None
        self.loaded = False
        if not isinstance(cas, str):
            raise PermissionError("CAS must be a bounded string")
        guard_cas(cas)
        if license_accepted is not True:
            raise PermissionError("model license acceptance required")
        if self.model_path is None:
            raise FileNotFoundError("GGUF model path is required")
        expected_sha256 = self.expected_sha256 if expected_sha256 is None else expected_sha256
        if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
                or any(c not in "0123456789abcdef" for c in expected_sha256)):
            raise ValueError("expected full SHA-256 digest required")
        if type(max_bytes) is not int or not _MIN_GGUF_BYTES <= max_bytes <= 64 * 1024**3:
            raise ValueError("invalid model byte budget")
        # Fail closed on platforms without secure descriptor-based path custody.
        if (not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW")
                or not hasattr(os, "supports_dir_fd")
                or os.open not in os.supports_dir_fd
                or os.stat not in os.supports_dir_fd):
            raise OSError("descriptor-relative secure model inspection unsupported")
        if ".." in self.model_path.parts or self.model_path.name in ("", ".", ".."):
            raise ValueError("GGUF path cannot traverse parent components")
        absolute = Path(os.path.abspath(os.fspath(self.model_path)))
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

        def open_parent() -> int:
            dfd = os.open(os.path.sep, directory_flags)
            try:
                for part in absolute.parts[1:-1]:
                    if part in ("", ".", ".."):
                        raise ValueError("invalid model parent component")
                    child = os.open(part, directory_flags, dir_fd=dfd)
                    os.close(dfd)
                    dfd = child
                return dfd
            except BaseException:
                os.close(dfd)
                raise

        dfd = open_parent()
        try:
            fd = os.open(absolute.name, flags, dir_fd=dfd)
        except BaseException:
            os.close(dfd)
            raise
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
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                    before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns):
                raise OSError("model changed during verification")
            if (path_after.st_dev, path_after.st_ino) != (after.st_dev, after.st_ino):
                raise OSError("model path replaced during verification")
            if total != before.st_size or path_after.st_nlink != 1:
                raise OSError("model read or link count changed during verification")
            # A renamed parent must not redirect file identity while the hash runs.
            reopened = open_parent()
            try:
                initial_parent = os.fstat(dfd)
                current_parent = os.fstat(reopened)
                if ((initial_parent.st_dev, initial_parent.st_ino) !=
                        (current_parent.st_dev, current_parent.st_ino)):
                    raise OSError("model parent changed during verification")
            finally:
                os.close(reopened)
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
            return {"status": "artifact_verified_only", "digest": self.digest,
                    "bytes": total}
        finally:
            os.close(fd)
            os.close(dfd)

    def verify(self, expected: str) -> bool:
        return self.loaded and self.digest == expected
