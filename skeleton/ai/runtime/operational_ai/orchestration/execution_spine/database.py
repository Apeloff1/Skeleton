"""One descriptor-rooted SQLite authority with WAL and bounded custody.

Metadata checks must not open/close a live SQLite database or WAL/SHM inode:
on POSIX that can silently release SQLite's process-associated file locks.
The owner-only directory is a trust boundary, not a hostile-same-UID sandbox.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .contracts import SpineError, IntegrityFailure
from .schema import DDL, SCHEMA_VERSION
from .path_policy import (
    open_private_root, private_file_at, private_stat_at, validate_private_sidecars,
)

_NAME = "ai-spine.sqlite"
_OPEN_GATE = threading.RLock()


class SpineDatabase:
    def __init__(self, root: str | Path, *, readonly: bool = False):
        if type(readonly) is not bool:
            raise SpineError("invalid read-only flag")
        if not Path("/proc/self/fd").is_dir():
            raise SpineError("Linux descriptor-backed SQLite required")
        self._root_fd = open_private_root(root)
        self._closed = False
        self._poisoned = False
        self._readonly = readonly
        self._lock = threading.RLock()
        try:
            # Serialize same-process first creation. Other processes compete
            # through O_EXCL and SQLite's own locking, never truncate a file.
            with _OPEN_GATE:
                validate_private_sidecars(self._root_fd, _NAME)
                try:
                    before = private_stat_at(self._root_fd, _NAME)
                except FileNotFoundError:
                    if readonly:
                        raise SpineError("read-only doctor will not create a missing database") from None
                    try:
                        fd = private_file_at(self._root_fd, _NAME, create=True)
                    except FileExistsError:
                        # Another process won exclusive creation; inspect it
                        # without opening or closing a live database descriptor.
                        pass
                    else:
                        os.close(fd)
                    before = private_stat_at(self._root_fd, _NAME)
                self._identity = (before.st_dev, before.st_ino)
                path = f"/proc/self/fd/{self._root_fd}/{_NAME}"
                # SQLite owns all live database and sidecar descriptors.
                uri = "file:" + path + ("?mode=ro" if readonly else "?mode=rw")
                self._db = sqlite3.connect(
                    uri, uri=True, isolation_level=None, timeout=10,
                    check_same_thread=False,
                )
                self._assert_custody()
                self._db.execute("PRAGMA busy_timeout=10000")
                self._db.execute("PRAGMA foreign_keys=ON")
                self._db.execute("PRAGMA trusted_schema=ON")
                self._db.execute("PRAGMA secure_delete=ON")
                if readonly:
                    self._db.execute("PRAGMA query_only=ON")
                else:
                    journal = self._db.execute("PRAGMA journal_mode=WAL").fetchone()
                    if journal != ("wal",):
                        raise SpineError("WAL unavailable")
                    self._db.execute("PRAGMA synchronous=FULL")
                    with self.transaction() as connection:
                        for sql in DDL:
                            connection.execute(sql)
                        connection.execute(
                            "INSERT OR IGNORE INTO controls VALUES ('schema_version',?)",
                            (str(SCHEMA_VERSION),),
                        )
                version = self._db.execute(
                    "SELECT value FROM controls WHERE control='schema_version'"
                ).fetchone()
                if version != (str(SCHEMA_VERSION),):
                    raise SpineError("unsupported database schema version")
                self.inspect()
        except BaseException:
            try:
                if hasattr(self, "_db"):
                    self._db.close()
            finally:
                os.close(self._root_fd)
                self._closed = True
            raise

    def _assert_custody(self) -> None:
        if self._closed or self._poisoned:
            raise SpineError("database unavailable")
        try:
            current = private_stat_at(self._root_fd, _NAME)
            if (current.st_dev, current.st_ino) != self._identity:
                raise IntegrityFailure("database identity changed")
            validate_private_sidecars(self._root_fd, _NAME)
        except (OSError, SpineError):
            self._poisoned = True
            raise

    def inspect(self):
        with self._lock:
            self._assert_custody()
            if self._db.execute("PRAGMA foreign_keys").fetchone() != (1,):
                raise IntegrityFailure("foreign keys disabled")
            if self._db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise IntegrityFailure("SQLite quick_check failed")
            if self._db.execute("PRAGMA foreign_key_check").fetchone():
                raise IntegrityFailure("foreign key mismatch")
            self._assert_custody()

    def _rollback(self) -> None:
        if self._db.in_transaction:
            try:
                self._db.execute("ROLLBACK")
            except sqlite3.Error as exc:
                self._poisoned = True
                raise IntegrityFailure("database rollback custody lost") from exc

    @contextmanager
    def transaction(self):
        if self._readonly:
            raise SpineError("read-only doctor cannot begin write transaction")
        with self._lock:
            self._assert_custody()
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
                self._assert_custody()
                self._db.execute("COMMIT")
            except BaseException:
                self._rollback()
                raise

    @contextmanager
    def snapshot(self):
        with self._lock:
            self._assert_custody()
            self._db.execute("BEGIN")
            try:
                yield self._db
                self._assert_custody()
            finally:
                self._rollback()

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                try:
                    self._db.close()
                finally:
                    os.close(self._root_fd)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
