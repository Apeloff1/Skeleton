"""Cross-process, descriptor-anchored session execution custody on Linux/POSIX.

SQLite CAS protects committed turns, but is insufficient to prevent two
processes from burning model cycles on the same pending request. A held flock
serializes any turn for the same session across independent service processes.
This is not distributed storage fencing or authorization, and does not make
external side effects safe. Production CLI always enables this guard.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import time
from typing import Iterator

from ...authority.identity import require_id
from ...model.gguf.file_guard import open_trusted_root


class SessionFenceError(RuntimeError):
    """Session writer ownership is unavailable or unsafe."""


class ProcessSessionFence:
    def __init__(self, root: Path | str) -> None:
        if os.name != 'posix' or not hasattr(fcntl, 'flock'):
            raise SessionFenceError('cross-process session fencing requires POSIX flock')
        self._root_fd = open_trusted_root(root)
        info = os.fstat(self._root_fd)
        if info.st_mode & 0o077:
            os.close(self._root_fd)
            raise SessionFenceError('session lock directory must be private 0700')
        self._closed = False

    @contextmanager
    def reserve(self, session: str, *, deadline_ms: int = 30000) -> Iterator[None]:
        require_id(session, field='conversation')
        if self._closed:
            raise SessionFenceError('fence closed')
        if type(deadline_ms) is not int or not 1 <= deadline_ms <= 600000:
            raise SessionFenceError('invalid bounded session lock deadline')
        filename = hashlib.sha256(session.encode('ascii')).hexdigest() + '.lock'
        fd = os.open(filename, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | getattr(os,'O_CLOEXEC',0),
                     0o600, dir_fd=self._root_fd)
        owned = False
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_mode & 0o077 or info.st_uid != os.getuid()):
                raise SessionFenceError('session lock file is not private, unique and owned')
            end = time.monotonic_ns() + deadline_ms * 1_000_000
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    owned = True
                    break
                except BlockingIOError as exc:
                    if time.monotonic_ns() >= end:
                        raise SessionFenceError('session writer deadline expired') from exc
                    time.sleep(min(.015, max(0,(end-time.monotonic_ns())/1e9)))
            yield
        finally:
            if owned:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def close(self) -> None:
        if not self._closed:
            self._closed=True
            os.close(self._root_fd)

    def __enter__(self) -> 'ProcessSessionFence':
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
