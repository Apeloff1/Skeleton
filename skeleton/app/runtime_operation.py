"""Cross-process admission for cooperating local installation operations.

A persistent, nonsecret lock inode serializes GUI, CLI and installer writes.
It is not a Docker daemon lock, distributed lease, or defense against a
hostile administrator. Never delete the lock file to recover an interruption:
the OS releases the held lock when the owning process exits.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import os
from pathlib import Path
import stat
import time

LOCK_NAME = ".env.operation.lock"
OPERATIONS = frozenset({"install", "setup", "start", "stop"})
_CONTENT = b"\0"


class RuntimeOperationDenied(RuntimeError):
    """Another operation owns the installation or its lock cannot be verified."""


def _directory_identity(info):
    if (not stat.S_ISDIR(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise RuntimeOperationDenied("installation root must be a real directory")
    return info.st_dev, info.st_ino


def _file_identity(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or getattr(info, "st_file_attributes", 0) & 0x400
            or info.st_size not in (0, 1)):
        raise RuntimeOperationDenied("runtime operation lock is unsafe; preserve it")
    if os.name != "nt" and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
        raise RuntimeOperationDenied("runtime operation lock must be owner-only")
    return info.st_dev, info.st_ino


def _try_lock(descriptor):
    if os.name == "nt":
        import msvcrt
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(descriptor):
    if os.name == "nt":
        import msvcrt
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(descriptor, fcntl.LOCK_UN)


@dataclass(frozen=True, slots=True)
class RuntimeOperation:
    root: Path
    operation: str
    descriptor: int
    directory_identity: tuple[int, int]
    file_identity: tuple[int, int]

    def current(self) -> bool:
        """Point-in-time custody check; never exposes file names or contents."""
        try:
            return (_directory_identity(self.root.lstat()) == self.directory_identity
                    and _file_identity(os.fstat(self.descriptor)) == self.file_identity
                    and _file_identity((self.root / LOCK_NAME).lstat()) == self.file_identity)
        except (OSError, RuntimeOperationDenied):
            return False


@contextmanager
def runtime_operation(root: Path, operation: str, *, wait_seconds: float = 0.25):
    """Acquire a stable OS-backed lease; release on all ordinary exit paths."""
    if operation not in OPERATIONS:
        raise ValueError("unknown runtime operation")
    if (type(wait_seconds) not in (float, int)
            or not 0 <= wait_seconds <= 10):
        raise ValueError("invalid runtime operation wait")
    descriptor = None
    acquired = False
    try:
        try:
            root = Path(root).absolute()
            directory = _directory_identity(root.lstat())
            path = root / LOCK_NAME
            flags = (os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
            # Reject special paths before open even on platforms without NOFOLLOW.
            try:
                _file_identity(path.lstat())
            except FileNotFoundError:
                pass
            descriptor = os.open(path, flags, 0o600)
            identity = _file_identity(os.fstat(descriptor))
            lease = RuntimeOperation(root, operation, descriptor, directory, identity)
            if not lease.current():
                raise RuntimeOperationDenied("runtime operation lock changed during admission")
            deadline = time.monotonic() + wait_seconds
            while True:
                try:
                    _try_lock(descriptor)
                    acquired = True
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeOperationDenied(
                            "another installation operation is active; retry after it finishes"
                        ) from None
                    time.sleep(min(remaining, 0.05))
            if not lease.current():
                raise RuntimeOperationDenied("runtime operation lock changed while waiting")
            # A persistent single byte makes Windows byte-range locking portable.
            # Initialize only after exclusivity; validate existing bytes.
            os.lseek(descriptor, 0, os.SEEK_SET)
            raw = os.read(descriptor, 2)
            if not raw:
                if os.write(descriptor, _CONTENT) != 1:
                    raise RuntimeOperationDenied("runtime operation lock initialization failed")
                os.fsync(descriptor)
            elif raw != _CONTENT:
                raise RuntimeOperationDenied("runtime operation lock contents invalid; preserve it")
            if not lease.current():
                raise RuntimeOperationDenied("runtime operation lock changed during initialization")
        except OSError:
            raise RuntimeOperationDenied("runtime operation unavailable; inspect installation permissions") from None
        yield lease
    finally:
        if descriptor is not None:
            try:
                if acquired:
                    _unlock(descriptor)
            finally:
                os.close(descriptor)


def compose_operation_environment(process_env, mode=None):
    """Keep lifecycle commands on the explicit Compose file and profile policy.

    Preserve operator-selected project names and Docker contexts for existing
    volume compatibility. Do not activate alternate env files or orphan removal.
    """
    result = dict(process_env)
    if mode is not None:
        result.update(mode)
    result.update(COMPOSE_REMOVE_ORPHANS="0", COMPOSE_DISABLE_ENV_FILE="0", COMPOSE_PROFILES="")
    result.pop("COMPOSE_ENV_FILES", None)
    return result
