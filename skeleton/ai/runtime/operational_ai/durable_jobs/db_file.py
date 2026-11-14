"""Private local SQLite custody for native AI work queues.

Uses a trusted owner-private directory and exact file identity checks. Python
SQLite's path-based connection is not a descriptor-anchored open; same-UID
hostility and full multi-process custody need independent OS qualification.
"""
from __future__ import annotations
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import stat
from typing import Iterator
from .errors import deny
from .spec import require_id, WorkLimits
from .store import JobStore


@contextmanager
def open_private_job_store(
    root: Path, leaf: str = "durable_jobs", *, limits: WorkLimits | None = None
) -> Iterator[JobStore]:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        deny("queue-private-posix-required")
    if not isinstance(root, Path):
        deny("queue-root-type")
    require_id(leaf, "queue-leaf")
    root_path = root.absolute()
    try:
        root_fd = os.open(root_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        deny("queue-root-unsafe")
    db = None
    try:
        root_stat = os.fstat(root_fd)
        if (not stat.S_ISDIR(root_stat.st_mode) or
                root_stat.st_uid != os.geteuid() or
                root_stat.st_mode & 0o077):
            deny("queue-root-public")
        filename = leaf + ".sqlite3"
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            fd = os.open(filename, flags, dir_fd=root_fd)
        except FileNotFoundError:
            try:
                fd = os.open(
                    filename, flags | os.O_CREAT | os.O_EXCL,
                    0o600, dir_fd=root_fd
                )
            except OSError:
                deny("queue-create-race")
        except OSError:
            deny("queue-file-unsafe")
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or before.st_nlink != 1 or before.st_mode & 0o077):
                deny("queue-file-permission")
            filename_path = root_path / filename
            visible = os.stat(filename_path, follow_symlinks=False)
            if (visible.st_dev, visible.st_ino) != (before.st_dev, before.st_ino):
                deny("queue-file-replaced")
            db = sqlite3.connect(
                filename_path, isolation_level=None,
                timeout=5, check_same_thread=False,
            )
            connected = os.stat(filename_path, follow_symlinks=False)
            if (connected.st_dev, connected.st_ino) != (before.st_dev, before.st_ino):
                deny("queue-connect-race")
        finally:
            os.close(fd)
        db.execute("PRAGMA journal_mode=WAL")
        yield JobStore(db, limits)
    finally:
        if db is not None:
            db.close()
        os.close(root_fd)
