"""Private POSIX SQLite bootstrap for canonical offline fair-stream custody.

The caller controls the directory and independent rollback anchor. This module
refuses symlinks, shared directories, hardlinks, untrusted owners and unsupported
platforms. It does not create keys, implement an external monotonic counter,
protect against a malicious same-UID process, or certify storage encryption.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Final
from urllib.parse import quote

MIN_DATABASE_BYTES: Final = 1 << 20
MAX_DATABASE_BYTES: Final = 1 << 30
_PAGE_BYTES: Final = 4096
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,75}\.db\Z", re.ASCII)


class PrivateSQLiteUnavailable(RuntimeError):
    """The required secure local filesystem or SQLite guarantees are absent."""


def _require_platform() -> None:
    if (
        os.name != "posix"
        or not hasattr(os, "geteuid")
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "supports_dir_fd")
        or os.open not in os.supports_dir_fd
    ):
        raise PrivateSQLiteUnavailable("secure POSIX dir-fd SQLite opener unavailable")


def _directory_fd(directory: str) -> int:
    """Traverse from root without following ANY component symlink."""
    if not directory.startswith("/") or "\x00" in directory:
        raise ValueError("absolute private database directory required")
    parts = directory.split("/")
    if any(part in (".", "..") for part in parts):
        raise ValueError("relative directory components forbidden")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    flags |= getattr(os, "O_CLOEXEC", 0)
    current = os.open("/", flags)
    try:
        for part in parts:
            if not part:
                continue
            next_fd = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = next_fd
        info = os.fstat(current)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            raise PrivateSQLiteUnavailable("private directory must be owned and mode 0700")
        return current
    except BaseException:
        os.close(current)
        raise


def _check_file(info: os.stat_result, max_bytes: int) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or info.st_mode & 0o777 != 0o600
        or info.st_size > max_bytes
    ):
        raise PrivateSQLiteUnavailable("untrusted private SQLite inode or file budget")


@dataclass(slots=True)
class PrivateSQLiteHandle:
    """Caller-owned lifetime for one verified SQLite connection and file descriptor."""

    connection: sqlite3.Connection
    _file_fd: int
    _directory_fd: int
    _filename: str
    _max_database_bytes: int
    _closed: bool = False

    def assert_current(self) -> None:
        """Revalidate the exact opened inode before sensitive operations.

        This catches rename/symlink replacement, permission changes and
        unexpected SQLite reattachment after the initial openat check.
        It does not defend against a malicious same-UID process racing
        between checks; app-account isolation is still mandatory.
        """
        if self._closed:
            raise PrivateSQLiteUnavailable("private SQLite handle closed")
        try:
            directory = os.fstat(self._directory_fd)
            if (not stat.S_ISDIR(directory.st_mode)
                    or directory.st_uid != os.geteuid()
                    or directory.st_mode & 0o077):
                raise PrivateSQLiteUnavailable("private directory custody changed")
            fd_info = os.fstat(self._file_fd)
            entry = os.stat(
                self._filename, dir_fd=self._directory_fd,
                follow_symlinks=False,
            )
            _check_file(fd_info, self._max_database_bytes)
            _check_file(entry, self._max_database_bytes)
            if (fd_info.st_dev, fd_info.st_ino) != (
                entry.st_dev, entry.st_ino,
            ):
                raise PrivateSQLiteUnavailable("SQLite path inode replaced")
            databases = self.connection.execute("PRAGMA database_list").fetchall()
            if (len(databases) != 1 or databases[0][1] != "main"
                    or not databases[0][2]):
                raise PrivateSQLiteUnavailable("unexpected SQLite attachment")
            actual = os.stat(databases[0][2], follow_symlinks=False)
            if (actual.st_dev, actual.st_ino) != (
                fd_info.st_dev, fd_info.st_ino,
            ):
                raise PrivateSQLiteUnavailable("SQLite backing inode changed")
            page_size = self.connection.execute("PRAGMA page_size").fetchone()[0]
            pages = self.connection.execute("PRAGMA page_count").fetchone()[0]
            if (type(page_size) is not int or type(pages) is not int
                    or pages * page_size > self._max_database_bytes):
                raise PrivateSQLiteUnavailable("SQLite page budget exceeded")
        except (OSError, sqlite3.Error) as exc:
            raise PrivateSQLiteUnavailable("private SQLite custody unavailable") from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.connection.close()
        finally:
            try:
                os.close(self._file_fd)
            finally:
                os.close(self._directory_fd)

    def __enter__(self) -> "PrivateSQLiteHandle":
        if self._closed:
            raise PrivateSQLiteUnavailable("private SQLite handle already closed")
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def open_private_sqlite(
    directory: str | os.PathLike[str],
    *,
    filename: str = "fair-stream.db",
    create: bool = False,
    max_database_bytes: int = 64 << 20,
) -> PrivateSQLiteHandle:
    """Open one owned database without implicit restart creation.

    This is an application bootstrap boundary, not a general-purpose opener.
    The final directory must already exist, belong to the effective UID and
    have no group/other access. Parent symlinks are rejected via openat.
    A trusted same-UID process can still mutate directory entries; this is
    NOT a sandbox against a compromised application account.

    The max-page-count bounds the main SQLite database, not temporary rollback
    journals, filesystem snapshots or the external high-watermark. The app
    must independently reserve disk and enforce overall storage quotas.
    """
    _require_platform()
    if type(filename) is not str or _SAFE_NAME.fullmatch(filename) is None:
        raise ValueError("bounded simple .db filename required")
    if type(create) is not bool:
        raise ValueError("explicit create boolean required")
    if (
        type(max_database_bytes) is not int
        or not MIN_DATABASE_BYTES <= max_database_bytes <= MAX_DATABASE_BYTES
    ):
        raise ValueError("bounded SQLite database byte budget required")
    if not isinstance(directory, (str, os.PathLike)):
        raise ValueError("private database directory required")
    raw = os.fspath(directory)
    if type(raw) is not str:
        raise ValueError("text-only database directory required")
    dir_fd = _directory_fd(raw)
    file_fd: int | None = None
    connection: sqlite3.Connection | None = None
    try:
        flags = os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        file_fd = os.open(filename, flags, 0o600, dir_fd=dir_fd)
        before = os.fstat(file_fd)
        _check_file(before, max_database_bytes)
        # The pathname is only used within an already validated private
        # directory. mode=rw forbids SQLite from creating a replacement.
        path = str(Path(raw) / filename)
        uri = "file:" + quote(path, safe="/") + "?mode=rw"
        connection = sqlite3.connect(
            uri, uri=True, timeout=1.0, isolation_level=None,
            check_same_thread=True,
        )
        after = os.stat(filename, dir_fd=dir_fd, follow_symlinks=False)
        opened = os.fstat(file_fd)
        _check_file(after, max_database_bytes)
        if (
            (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino)
        ):
            raise PrivateSQLiteUnavailable("SQLite inode changed during open")
        # The connection must point to the same inode, not an alternate URI.
        db_list = connection.execute("PRAGMA database_list").fetchall()
        if len(db_list) != 1 or db_list[0][1] != "main":
            raise PrivateSQLiteUnavailable("unexpected SQLite attached database")
        db_path = db_list[0][2]
        try:
            db_info = os.stat(db_path, follow_symlinks=False)
        except OSError as exc:
            raise PrivateSQLiteUnavailable("SQLite backing path unavailable") from exc
        if (db_info.st_dev, db_info.st_ino) != (before.st_dev, before.st_ino):
            raise PrivateSQLiteUnavailable("SQLite opened a different inode")
        if before.st_size == 0:
            connection.execute("PRAGMA page_size = 4096")
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        if type(page_size) is not int or page_size < 512 or page_size > 65536:
            raise PrivateSQLiteUnavailable("unsupported SQLite page size")
        max_pages = max_database_bytes // page_size
        if max_pages < 1:
            raise PrivateSQLiteUnavailable("SQLite page budget exhausted")
        actual_pages = connection.execute(
            "PRAGMA max_page_count = " + str(max_pages)
        ).fetchone()[0]
        if actual_pages > max_pages:
            raise PrivateSQLiteUnavailable("SQLite page-count cap not applied")
        if connection.execute("PRAGMA page_count").fetchone()[0] > max_pages:
            raise PrivateSQLiteUnavailable("existing database exceeds page budget")
        mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
        if mode.lower() != "delete":
            raise PrivateSQLiteUnavailable("durable rollback journal mode unavailable")
        connection.execute("PRAGMA synchronous = FULL")
        if connection.execute("PRAGMA synchronous").fetchone()[0] != 2:
            raise PrivateSQLiteUnavailable("durable SQLite synchronous mode unavailable")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA busy_timeout = 1000")
        connection.execute("PRAGMA journal_size_limit = 65536")
        if connection.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
            raise PrivateSQLiteUnavailable("SQLite integrity check failed")
        return PrivateSQLiteHandle(
            connection, file_fd, dir_fd, filename, max_database_bytes,
        )
    except BaseException:
        if connection is not None:
            connection.close()
        if file_fd is not None:
            os.close(file_fd)
        os.close(dir_fd)
        raise
