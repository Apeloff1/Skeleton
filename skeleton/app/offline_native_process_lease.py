"""Explicit same-host process exclusion for cooperating measured CPU deployments.

An operator must provision one private shared directory and keep its lock
inode stable. No filesystem-wide memory reservation is claimed. On POSIX the
inherited open file description retains its flock across parent death only
while a native child actually retains that descriptor.
"""
from __future__ import annotations

import errno
import os
from pathlib import Path
import stat
import threading
from typing import Callable


class NativeLeaseError(RuntimeError):
    """A cooperating native process cannot safely acquire the shared slot."""


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


class NativeProcessLease:
    """Idempotent parent reference release; never explicitly unlock the OFD."""

    def __init__(self, fd: int, identity: tuple[int, int],
                 released: Callable[[], None]) -> None:
        self._fd: int | None = fd
        self._identity = identity
        self._released = released
        self._lock = threading.RLock()

    def child_pass_fds(self) -> tuple[int, ...]:
        with self._lock:
            fd = self._fd
            if fd is None or _identity(os.fstat(fd)) != self._identity:
                raise NativeLeaseError("native lease descriptor no longer matches its owner")
            return (fd,)

    def __call__(self) -> None:
        with self._lock:
            fd = self._fd
            if fd is None:
                return
            # Closing this parent reference does not unlock a child reference.
            # Never use LOCK_UN: it would release the entire shared OFD.
            if _identity(os.fstat(fd)) != self._identity:
                raise NativeLeaseError("native lease descriptor changed before release")
            self._fd = None
            os.close(fd)
            self._released()


class NativeCpuLeaseOwner:
    """One cooperating local native child slot across all configured processes."""

    LOCK_NAME = "native-cpu.lock"

    def __init__(self, directory: Path, recheck: Callable[[], None]) -> None:
        if not isinstance(directory, Path) or not directory.is_absolute() or not callable(recheck):
            raise NativeLeaseError("absolute trusted lease directory and resource check required")
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            raise NativeLeaseError("POSIX descriptor-backed native lease unavailable")
        self._directory = directory
        self._recheck = recheck
        self._lock = threading.RLock()
        self._acquired = 0
        self._released = 0
        self._denied = 0
        self._directory_identity = self._inspect_directory()
        self._lock_identity: tuple[int, int] | None = None

    def _inspect_directory(self) -> tuple[int, int]:
        try:
            if self._directory.resolve(strict=True) != self._directory:
                raise NativeLeaseError("lease directory must have a canonical nonsymlink path")
            info = self._directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077):
                raise NativeLeaseError("lease directory must be private and owned by the service user")
            return _identity(info)
        except (OSError, ValueError) as exc:
            raise NativeLeaseError("lease directory unavailable") from exc

    def _check_file(self, dirfd: int, fd: int) -> tuple[int, int]:
        opened = os.fstat(fd)
        named = os.stat(self.LOCK_NAME, dir_fd=dirfd, follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid()
                or opened.st_nlink != 1 or opened.st_mode & 0o077
                or opened.st_size != 0 or _identity(opened) != _identity(named)):
            raise NativeLeaseError("lease file identity or private-file policy mismatch")
        observed = _identity(opened)
        if self._lock_identity is not None and observed != self._lock_identity:
            raise NativeLeaseError("native lease inode changed after activation")
        if (self._inspect_directory() != self._directory_identity
                or _identity(os.fstat(dirfd)) != self._directory_identity):
            raise NativeLeaseError("native lease directory changed after activation")
        return observed

    def acquire(self) -> NativeProcessLease:
        """Acquire nonblocking exclusion, then revalidate resource headroom."""
        import fcntl

        with self._lock:
            dirfd = fd = None
            try:
                if self._inspect_directory() != self._directory_identity:
                    raise NativeLeaseError("native lease directory changed after activation")
                dirfd = os.open(self._directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                fd = os.open(self.LOCK_NAME, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
                             | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0),
                             0o600, dir_fd=dirfd)
                observed = self._check_file(dirfd, fd)
                self._lock_identity = observed
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    if exc.errno in (errno.EACCES, errno.EAGAIN):
                        raise NativeLeaseError("native process slot is already held") from exc
                    raise
                self._check_file(dirfd, fd)
                self._recheck()
                self._check_file(dirfd, fd)
                def released() -> None:
                    with self._lock:
                        self._released += 1
                lease = NativeProcessLease(fd, observed, released)
                self._acquired += 1
                fd = None
                return lease
            except BaseException as exc:
                self._denied += 1
                if isinstance(exc, OSError):
                    raise NativeLeaseError("native process slot unavailable") from exc
                raise
            finally:
                if fd is not None:
                    os.close(fd)
                if dirfd is not None:
                    os.close(dirfd)

    def status(self) -> dict:
        with self._lock:
            return {"scope": "cooperating_deployments_same_lock_inode",
                    "acquired": self._acquired, "released": self._released,
                    "denied": self._denied, "owned_parent_references": self._acquired - self._released,
                    "physical_memory_reserved": False, "child_retention_qualified": False}
