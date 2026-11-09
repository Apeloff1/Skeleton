"""POSIX descriptor-anchored filesystem operations for the compressed vault.

A pathname check cannot protect a later open from symlink swaps. Every file
operation here is relative to a directory descriptor, obtained by walking each
absolute path component with O_NOFOLLOW and O_DIRECTORY.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import os
from pathlib import Path
import secrets
import stat
from typing import BinaryIO, Callable, Iterator


class VaultPathError(ValueError):
    """Unsafe filesystem state or unsupported descriptor semantics."""


def _directory_flags() -> int:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise VaultPathError("secure vault requires POSIX directory descriptors")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


@contextmanager
def anchored_directory(path: Path) -> Iterator[int]:
    """Open every path component without following symlinks, holding final fd."""
    root = Path(os.path.abspath(path))
    if not root.is_absolute():
        raise VaultPathError("vault directory must be absolute")
    flags = _directory_flags()
    fd = os.open("/", flags)
    try:
        for part in root.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def ensure_directory(path: Path) -> Path:
    """Safely create missing path components relative to pinned parents."""
    root = Path(os.path.abspath(path))
    flags = _directory_flags()
    fd = os.open("/", flags)
    try:
        for part in root.parts[1:]:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    # Another process created this component concurrently.
                    # The descriptor reopen still rejects symlinks/unsafe types.
                    pass
                next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return root
    finally:
        os.close(fd)


def _safe_file(fd: int, name: str, *, max_bytes: int | None = None) -> int:
    if not name or "/" in name or name in {".", ".."} or "\x00" in name:
        raise VaultPathError("invalid vault filename")
    flags = (os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NONBLOCK", 0))
    opened = os.open(name, flags, dir_fd=fd)
    try:
        info = os.fstat(opened)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise VaultPathError("vault source is not a private regular file")
        if max_bytes is not None and info.st_size > max_bytes:
            raise VaultPathError("vault file exceeds compressed byte budget")
        return opened
    except BaseException:
        os.close(opened)
        raise


@contextmanager
def read_regular(fd: int, name: str, *, max_bytes: int | None = None) -> Iterator[BinaryIO]:
    opened = _safe_file(fd, name, max_bytes=max_bytes)
    with os.fdopen(opened, "rb") as handle:
        yield handle


def _reject_unsafe_existing(fd: int, name: str) -> None:
    try:
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise VaultPathError("vault destination is a link or non-regular file")


class _BoundedSink:
    """Enforce disk-output limits before each write rather than after close."""

    def __init__(self, handle: BinaryIO, max_bytes: int):
        if type(max_bytes) is not int or max_bytes < 0:
            raise VaultPathError("invalid vault output byte budget")
        self._handle = handle
        self._remaining = max_bytes

    def write(self, data) -> int:
        if len(data) > self._remaining:
            raise VaultPathError("vault output exceeds compressed byte budget")
        written = self._handle.write(data)
        self._remaining -= written
        return written

    def writelines(self, lines) -> None:
        # File-like callers may use writelines instead of write; each emitted
        # chunk must pass through the same byte budget.
        for line in lines:
            self.write(line)

    def __getattr__(self, name: str):
        # Do not expose alternate handles that would bypass write accounting.
        if name in {"raw", "buffer", "detach"}:
            raise AttributeError(name)
        return getattr(self._handle, name)


def atomic_write(fd: int, name: str, writer: Callable[[BinaryIO], None], *, max_bytes: int | None = None) -> int:
    """Publish complete bytes under a fresh private name, then fsync and rename.

    A failing writer never truncates an existing destination. The directory
    descriptor remains fixed even if an attacker replaces its pathname.
    """
    if not name or "/" in name or name in {".", ".."}:
        raise VaultPathError("invalid vault filename")
    temp = ".vault-part-" + secrets.token_hex(16)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    opened = os.open(temp, flags, 0o600, dir_fd=fd)
    published = False
    try:
        # Keep the descriptor alive even when compression closes its writer.
        with os.fdopen(opened, "wb", closefd=False) as handle:
            sink = _BoundedSink(handle, max_bytes) if max_bytes is not None else handle
            writer(sink)
            if not handle.closed:
                handle.flush()
        os.fsync(opened)
        written = os.fstat(opened).st_size
        if max_bytes is not None and written > max_bytes:
            raise VaultPathError("vault output exceeds compressed byte budget")
        _reject_unsafe_existing(fd, name)
        os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
        published = True
        os.fsync(fd)
        return written
    finally:
        os.close(opened)
        if not published:
            try:
                os.unlink(temp, dir_fd=fd)
            except FileNotFoundError:
                pass


def _copy_bounded(source: BinaryIO, destination: BinaryIO, *, max_bytes: int) -> None:
    """Reject a growing source before copying more than the admitted budget.

    An initial fstat size check is insufficient: another process can append to
    the already-open source after inspection. Never read or write beyond the
    admission budget, including a one-byte probe for excess source content.
    """
    if type(max_bytes) is not int or max_bytes < 0:
        raise VaultPathError("invalid vault backup byte budget")
    remaining = max_bytes
    while True:
        chunk = source.read(min(1024 * 1024, remaining + 1))
        if not chunk:
            return
        if len(chunk) > remaining:
            raise VaultPathError("vault backup exceeds compressed byte budget")
        destination.write(chunk)
        remaining -= len(chunk)


def snapshot_regular(fd: int, name: str, *, max_bytes: int) -> str | None:
    """Keep a private bounded copy before a canonical shard overwrite.

    An existing leaf must be regular, single-link and no larger than the
    caller's budget. A concurrently growing source remains bounded as copied.
    """
    with ExitStack() as stack:
        try:
            # Only a missing ORIGINAL shard means there is nothing to back up.
            # A FileNotFoundError during publication must fail closed.
            source = stack.enter_context(
                read_regular(fd, name, max_bytes=max_bytes),
            )
        except FileNotFoundError:
            return None
        backup = ".vault-backup-" + secrets.token_hex(16)
        atomic_write(
            fd, backup,
            lambda destination: _copy_bounded(
                source, destination, max_bytes=max_bytes,
            ),
            max_bytes=max_bytes,
        )
        return backup


def unlink_regular(fd: int, name: str) -> None:
    """Remove only a regular single-link leaf; never follow its pathname."""
    _reject_unsafe_existing(fd, name)
    os.unlink(name, dir_fd=fd)
    os.fsync(fd)
