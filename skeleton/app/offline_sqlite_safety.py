"""Low-level SQLite file admission checks for the offline app shell.

SQLite may open -wal, -shm or -journal companions next to the selected file.
Before connecting, reject symlink/redirection and special-file companions so
a user-selected database folder cannot trivially redirect these accesses.
This is defense in depth, not a guarantee against concurrent same-user
filesystem mutation or privileged OS compromise.
"""
from __future__ import annotations

from pathlib import Path


SIDECARS = ("-wal", "-shm", "-journal")


class UnsafeOfflineSqlitePath(RuntimeError):
    """The selected SQLite database has an unsafe companion path."""


def check_sqlite_companion_paths(path: str | Path) -> None:
    selected = Path(path).expanduser()
    for suffix in SIDECARS:
        candidate = Path(str(selected) + suffix)
        if candidate.is_symlink() or (
            candidate.exists() and not candidate.is_file()
        ):
            raise UnsafeOfflineSqlitePath(
                "SQLite companion file is redirected or not regular: " + suffix
            )


__all__ = [
    "SIDECARS", "UnsafeOfflineSqlitePath", "check_sqlite_companion_paths",
]
