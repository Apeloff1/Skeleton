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


def _open_guarded_model(path: Path) -> tuple[int, int]:
    """Open a model using no-follow descriptors for every parent component.

    This is a POSIX-only qualification boundary. Unsupported hosts fail closed;
    portable consumer packaging does not imply that model weights were loaded.
    The caller owns both returned descriptors, file first and directory second.
    """
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or
            not hasattr(os, "O_DIRECTORY") or not hasattr(os, "supports_dir_fd") or os.open not in os.supports_dir_fd):
        raise OSError("descriptor-anchored model custody unavailable")
    parts = Path(os.path.abspath(os.fspath(path))).parts
    if len(parts) < 2:
        raise OSError("model path does not name a regular file")
    directory = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in parts[1:-1]:
            nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                          dir_fd=directory)
            os.close(directory)
            directory = nxt
        model = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW |
                        getattr(os, "O_NONBLOCK", 0) |
                        getattr(os, "O_CLOEXEC", 0),
                        dir_fd=directory)
        return model, directory
    except BaseException:
        os.close(directory)
        raise



class ModelLoader:
    """Legacy artifact inspector; never simulates a successful model load."""

    def __init__(self, model_path: Optional[str] = None, *,
                 expected_sha256: Optional[str] = None,
                 license_accepted: bool = False,
                 max_bytes: int = 64 * 1024**3):
        self.model_path = Path(model_path) if model_path else None
        self.expected_sha256 = expected_sha256
        self.license_accepted = license_accepted
        self.max_bytes = max_bytes
        self.digest: Optional[str] = None
        self.loaded = False

    def load(self, cas: str, *, expected_sha256: str | None = None,
             license_accepted: bool | None = None,
             max_bytes: int | None = None) -> dict:
        self.digest = None
        self.loaded = False
        guard_cas(cas)
        expected_sha256 = self.expected_sha256 if expected_sha256 is None else expected_sha256
        license_accepted = self.license_accepted if license_accepted is None else license_accepted
        max_bytes = self.max_bytes if max_bytes is None else max_bytes
        if license_accepted is not True:
            raise PermissionError("model license acceptance required")
        if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
                or any(c not in "0123456789abcdef" for c in expected_sha256)):
            raise ValueError("expected full SHA-256 digest required")
        if type(max_bytes) is not int or not _GGUF_HEADER_SIZE <= max_bytes <= 64 * 1024**3:
            raise ValueError("invalid model byte budget")
        if self.model_path is None:
            raise FileNotFoundError("GGUF model path is required")
        # Refuse symlinked ancestry, special nodes, and final-component races.
        fd, parent_fd = _open_guarded_model(self.model_path)
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
            # Rewalk *all* directory components at publish time, not only the
            # basename: a replaced ancestor must not rebind this receipt.
            current_fd, current_parent_fd = _open_guarded_model(self.model_path)
            try:
                current = os.fstat(current_fd)
                if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                        or (current.st_dev, current.st_ino, current.st_size,
                            current.st_mtime_ns, current.st_ctime_ns) !=
                           (after.st_dev, after.st_ino, after.st_size,
                            after.st_mtime_ns, after.st_ctime_ns)):
                    raise OSError("model path rebound during verification")
            finally:
                os.close(current_fd)
                os.close(current_parent_fd)
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
            os.close(parent_fd)

    def verify(self, expected: str) -> bool:
        return self.loaded and self.digest == expected
