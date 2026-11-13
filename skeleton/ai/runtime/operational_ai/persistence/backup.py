"""Create-only SQLite snapshot with physical database integrity verification."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
from .journal import EventJournal, JournalError


def snapshot(journal: EventJournal, destination: str | Path) -> dict[str, object]:
    target=Path(destination).absolute()
    if target.exists() or target.is_symlink():
        raise JournalError("backup target already exists")
    if not target.parent.is_dir() or target.parent.is_symlink():
        raise JournalError("backup directory invalid")
    fd,temp=tempfile.mkstemp(dir=str(target.parent),prefix=".ai-journal-",suffix=".partial")
    os.close(fd)
    try:
        output=sqlite3.connect(temp)
        try:
            with journal._lock:
                journal._db.backup(output)
            if output.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise JournalError("backup failed SQLite integrity check")
        finally:
            output.close()
        with open(temp,"rb") as src:
            digest=hashlib.file_digest(src,"sha256").hexdigest()
        if target.exists() or target.is_symlink():
            raise JournalError("backup target appeared during publication")
        os.chmod(temp,0o600)
        os.link(temp,target)  # no-clobber create-only publication
        with open(target,"rb") as file:
            os.fsync(file.fileno())
        return {"path":str(target),"bytes":target.stat().st_size,"sha256":digest,
                "state":"integrity-checked-not-encrypted"}
    finally:
        Path(temp).unlink(missing_ok=True)
