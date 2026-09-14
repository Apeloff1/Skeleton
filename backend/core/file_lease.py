"""Small cross-platform advisory file lease for multi-process critical sections."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import threading
from typing import Iterator

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None
try:
    import msvcrt  # type: ignore
except ImportError:  # pragma: no cover
    msvcrt = None


class FileLeaseUnavailable(RuntimeError):
    pass


class FileLease:
    """Process-wide advisory mutex backed by a stable filesystem path.

    Thread serialization is included because Windows byte-range locks are not a
    substitute for an in-process mutex. All users of the same path coordinate
    across processes on POSIX and Windows.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock = threading.RLock()

    @property
    def backend(self) -> str:
        if fcntl is not None:
            return "fcntl"
        if msvcrt is not None:
            return "msvcrt"
        return "unavailable"

    @contextmanager
    def acquire(self) -> Iterator[None]:
        with self._thread_lock:
            with self.path.open("a+b") as handle:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                    try:
                        yield
                    finally:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    return
                if msvcrt is not None:  # pragma: no cover - Windows
                    handle.seek(0, os.SEEK_END)
                    if handle.tell() == 0:
                        handle.write(b"\0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    try:
                        yield
                    finally:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    return
                raise FileLeaseUnavailable("no supported OS file-locking primitive available")
