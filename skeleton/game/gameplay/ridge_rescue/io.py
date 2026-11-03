"""Descriptor-anchored bounded IO for source, save and portable game exports.

POSIX only: on platforms without no-follow directory-descriptor operations,
fail closed instead of silently following symlinks or using unsafe fallbacks.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat

from .custody import canonical

MAX_PATH_BYTES = 4096
MAX_COMPONENT_BYTES = 255


class IOErrorBounded(ValueError):
    pass


def _supported() -> None:
    required = ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC")
    if any(not hasattr(os, key) for key in required) or os.open not in os.supports_dir_fd:
        raise IOErrorBounded("descriptor-anchored file IO unsupported on this platform")
    if os.stat not in os.supports_dir_fd or os.unlink not in os.supports_dir_fd or os.link not in os.supports_dir_fd:
        raise IOErrorBounded("atomic file IO unsupported on this platform")


def _parent(path: str | Path) -> tuple[int, str]:
    _supported()
    try:
        name = os.fspath(path)
    except TypeError as exc:
        raise IOErrorBounded("invalid path") from exc
    if not isinstance(name, str) or not name or "\x00" in name:
        raise IOErrorBounded("invalid path")
    try:
        raw = name.encode("utf-8")
    except UnicodeError as exc:
        raise IOErrorBounded("path is not UTF-8") from exc
    if len(raw) > MAX_PATH_BYTES:
        raise IOErrorBounded("path too long")
    absolute = name.startswith("/")
    parts = name.split("/")
    if absolute:
        parts = parts[1:]
    if not parts or any(not p or p in (".", "..") or len(p.encode("utf-8")) > MAX_COMPONENT_BYTES for p in parts):
        raise IOErrorBounded("unsafe path component")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open("/" if absolute else ".", flags)
        try:
            for part in parts[:-1]:
                next_fd = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            return fd, parts[-1]
        except BaseException:
            os.close(fd)
            raise
    except OSError as exc:
        raise IOErrorBounded("unsafe parent directory") from exc


def read_bounded(path: str | Path, limit: int = 256_000) -> bytes:
    if type(limit) is not int or not 0 <= limit <= 1_000_000:
        raise IOErrorBounded("invalid read limit")
    parent, leaf = _parent(path)
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | getattr(os, "O_NONBLOCK", 0)
        try:
            fd = os.open(leaf, flags, dir_fd=parent)
        except OSError as exc:
            raise IOErrorBounded("input open refused") from exc
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size < 0 or before.st_size > limit:
                raise IOErrorBounded("input must be a bounded regular file")
            chunks: list[bytes] = []
            count = 0
            while True:
                part = os.read(fd, min(65_536, limit + 1 - count))
                if not part:
                    break
                count += len(part)
                if count > limit:
                    raise IOErrorBounded("input exceeds byte limit")
                chunks.append(part)
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ):
                raise IOErrorBounded("input changed during read")
            return b"".join(chunks)
        finally:
            os.close(fd)
    except OSError as exc:
        raise IOErrorBounded("input read refused") from exc
    finally:
        os.close(parent)


def write_new(path: str | Path, value: object, limit: int = 256_000) -> None:
    if type(limit) is not int or not 0 <= limit <= 1_000_000:
        raise IOErrorBounded("invalid output limit")
    payload = canonical(value) + b"\n"
    if len(payload) > limit:
        raise IOErrorBounded("output exceeds byte limit")
    parent, leaf = _parent(path)
    temporary = ".ridge-" + secrets.token_hex(16) + ".tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = None
    created = None
    try:
        fd = os.open(temporary, flags, 0o600, dir_fd=parent)
        created = os.fstat(fd)
        if not stat.S_ISREG(created.st_mode) or created.st_nlink != 1:
            raise IOErrorBounded("unsafe temporary output")
        with os.fdopen(fd, "wb") as output:
            fd = None
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        # Hard-link publication is atomic and fails if the destination exists.
        # Never use os.replace or a rename that could overwrite a user save.
        os.link(temporary, leaf, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        os.fsync(parent)
    except OSError as exc:
        raise IOErrorBounded("refuse overwrite or unsafe output") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if created is not None:
            try:
                current = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                    os.unlink(temporary, dir_fd=parent)
                    os.fsync(parent)
            except FileNotFoundError:
                pass
        os.close(parent)
