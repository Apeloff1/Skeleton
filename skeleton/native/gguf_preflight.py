"""Bounded source-only GGUF framing and SHA inspection under descriptor custody.

This is NOT full GGUF parsing, tensor admission, license approval, tokenizer
verification, loading, device qualification or inference readiness. A caller
must independently bind the approved model and operator before runtime use.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import stat
import struct


class GGUFPreflightError(ValueError):
    """Model bytes cannot be admitted for further independent qualification."""


@dataclass(frozen=True)
class GGUFHeader:
    version: int
    tensor_count: int
    metadata_count: int
    file_size: int
    sha256: str


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_nlink, info.st_uid, info.st_gid,
            info.st_mtime_ns, info.st_ctime_ns)


def _open_beneath_trusted_parent(path: str | Path) -> tuple[int, int, str]:
    """Pin each parent inode; refuse symlinks and writable parent directories."""
    if (os.name != "posix" or not hasattr(os, "O_DIRECTORY")
            or not hasattr(os, "O_NOFOLLOW")
            or os.open not in os.supports_dir_fd
            or os.stat not in os.supports_dir_fd):
        raise GGUFPreflightError("POSIX descriptor-bound no-follow custody unavailable")
    raw = os.fspath(path)
    if (type(raw) is not str or not raw or len(raw) > 4096 or
            "\x00" in raw or "\\" in raw or
            any(part in (".", "..") for part in raw.split("/"))):
        raise GGUFPreflightError("unsafe or noncanonical model path")
    try:
        absolute = raw if os.path.isabs(raw) else os.path.join(os.getcwd(), raw)
        pieces = [part for part in absolute.split("/") if part]
        if not pieces:
            raise GGUFPreflightError("missing model filename")
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        parent_fd = os.open("/", directory_flags)
        file_fd = None
        try:
            if os.fstat(parent_fd).st_mode & 0o022:
                raise GGUFPreflightError("untrusted writable root")
            for name in pieces[:-1]:
                next_fd = os.open(name, directory_flags, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = next_fd
                info = os.fstat(parent_fd)
                if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
                    raise GGUFPreflightError("untrusted writable model parent")
            file_flags = (os.O_RDONLY | os.O_NOFOLLOW
                          | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0))
            file_fd = os.open(pieces[-1], file_flags, dir_fd=parent_fd)
            return parent_fd, file_fd, pieces[-1]
        except BaseException:
            if file_fd is not None:
                os.close(file_fd)
            os.close(parent_fd)
            raise
    except GGUFPreflightError:
        raise
    except OSError as exc:
        raise GGUFPreflightError("model file or parent unavailable or unsafe") from exc


def inspect_gguf(
    path: str | Path,
    *,
    expected_sha256: str,
    max_bytes: int = 128 * 1024 * 1024 * 1024,
    max_tensors: int = 1_000_000,
    max_metadata: int = 1_000_000,
) -> GGUFHeader:
    """Inspect a complete, private, immutable regular file by exact source SHA.

    A syntactically plausible header alone does not qualify any model.
    """
    if (type(expected_sha256) is not str or len(expected_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_sha256)):
        raise GGUFPreflightError("expected_sha256 must be lowercase SHA-256")
    for value in (max_bytes, max_tensors, max_metadata):
        if type(value) is not int or value <= 0:
            raise GGUFPreflightError("limits must be positive integers")

    parent_fd, file_fd, name = _open_beneath_trusted_parent(path)
    try:
        before = os.fstat(file_fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_size < 24 or before.st_size > max_bytes):
            raise GGUFPreflightError("model file size/type rejected")
        if before.st_nlink != 1 or before.st_mode & 0o022:
            raise GGUFPreflightError("model source permissions or hardlink unsafe")
        header = os.read(file_fd, 24)
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
            block = os.read(file_fd, min(1024 * 1024, max_bytes - total + 1))
            if not block:
                break
            total += len(block)
            if total > max_bytes:
                raise GGUFPreflightError("model exceeds byte budget")
            digest.update(block)

        after_fd = os.fstat(file_fd)
        try:
            after_path = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise GGUFPreflightError("model source path changed during inspection") from exc
        if (_identity(before) != _identity(after_fd)
                or _identity(before) != _identity(after_path)
                or not stat.S_ISREG(after_path.st_mode)
                or total != before.st_size):
            raise GGUFPreflightError("model source changed during inspection")
        actual = digest.hexdigest()
        if not hmac.compare_digest(actual, expected_sha256):
            raise GGUFPreflightError("model SHA-256 mismatch")
        return GGUFHeader(version, tensors, metadata, total, actual)
    except OSError as exc:
        raise GGUFPreflightError("model source read or reinspection failed") from exc
    finally:
        os.close(file_fd)
        os.close(parent_fd)
