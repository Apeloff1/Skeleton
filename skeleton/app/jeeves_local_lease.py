"""Crash-released, cross-process execution lease for one local Jeeves workspace.

The SQLite transcript remains authoritative. This sidecar lock ONLY protects
the interval between a new local model admission, native inference and durable
receipt verification from two independent service processes on one machine.
It is never interpreted as a model attestation, a network sandbox or a remote
distributed lock. Its file must remain on the same local disk as the database.

The lock is deliberately persistent: removing a lockfile after releasing a
flock permits old waiters to hold a different inode, destroying exclusion.
No prompt, bearer token, PID, model path or process diagnostics are written.
"""
from __future__ import annotations

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import stat
import threading
from typing import Iterator


class LocalInferenceLeaseBusy(RuntimeError):
    """A peer with the same local database owns the generation slot."""


class LocalInferenceLeaseUnavailable(RuntimeError):
    """The local host cannot prove exclusive inference ownership."""


class LocalInferenceLease:
    """Non-blocking single-host lease with mandatory descriptor-based custody.

    POSIX uses flock over a pinned file descriptor. Windows uses non-blocking
    msvcrt byte-range locking. Both are released by the kernel after process
    death. Every open checks regular-file identity, link count and POSIX owner
    permissions. No in-process counter or TTL can substitute for OS exclusion.
    """

    def __init__(self, database: str | Path) -> None:
        if not isinstance(database, (str, Path)) or str(database) in ("", ":memory:"):
            raise LocalInferenceLeaseUnavailable("persistent local SQLite workspace required")
        database_path = Path(database).expanduser().resolve(strict=False)
        if not database_path.is_absolute():
            raise LocalInferenceLeaseUnavailable("local workspace must resolve to an absolute path")
        self.path = database_path.with_name(database_path.name + ".inference.lock")
        self._thread_gate = threading.Lock()

    def _verified_descriptor(self) -> int:
        flags = os.O_CREAT | os.O_RDWR
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_BINARY", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError as exc:
            raise LocalInferenceLeaseUnavailable("private inference lease cannot be opened") from exc
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise LocalInferenceLeaseUnavailable("inference lease is not a private regular file")
            if os.name == "posix" and (
                metadata.st_uid != os.getuid() or metadata.st_mode & 0o077
            ):
                raise LocalInferenceLeaseUnavailable("inference lease owner permissions are unsafe")
            # O_NOFOLLOW is absent on some hosts. Compare a fresh lstat with
            # the already-opened descriptor rather than trusting a path alone.
            observed = self.path.lstat()
            if (not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1
                    or (observed.st_dev, observed.st_ino)
                    != (metadata.st_dev, metadata.st_ino)):
                raise LocalInferenceLeaseUnavailable("inference lease identity changed during admission")
            # Windows locks an exact byte range; establish its byte without
            # truncation. No user information or host secrets enter this file.
            if metadata.st_size == 0:
                os.write(fd, b"\\0")
                os.fsync(fd)
            elif metadata.st_size != 1:
                raise LocalInferenceLeaseUnavailable("inference lease marker format is invalid")
            return fd
        except BaseException:
            os.close(fd)
            raise

    @staticmethod
    def _lock_fd(fd: int) -> None:
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            elif os.name == "posix":
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                raise LocalInferenceLeaseUnavailable("unsupported local operating system lock")
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                raise LocalInferenceLeaseBusy("local inference lease is already owned") from None
            raise LocalInferenceLeaseUnavailable("local inference lease could not be acquired") from exc

    @staticmethod
    def _unlock_fd(fd: int) -> None:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        elif os.name == "posix":
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)

    @contextmanager
    def hold(self) -> Iterator[None]:
        """Hold OS exclusion through local inference *and* SQLite commit.

        A busy lease fails quickly; it never starts a second GGUF worker. A
        crash or forced process exit closes the kernel descriptor automatically.
        """
        if not self._thread_gate.acquire(blocking=False):
            raise LocalInferenceLeaseBusy("local inference is already running in this service")
        fd: int | None = None
        locked = False
        try:
            fd = self._verified_descriptor()
            self._lock_fd(fd)
            locked = True
            yield
        finally:
            if fd is not None:
                try:
                    if locked:
                        self._unlock_fd(fd)
                finally:
                    os.close(fd)
            self._thread_gate.release()


__all__ = [
    "LocalInferenceLease",
    "LocalInferenceLeaseBusy",
    "LocalInferenceLeaseUnavailable",
]
