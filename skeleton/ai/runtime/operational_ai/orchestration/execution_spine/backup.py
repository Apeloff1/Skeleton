"""Explicit, bounded, no-clobber database backups via SQLite online backup API.

Backups are private operator-managed SQLite files, not Git artifacts. Publication
is never claimed after an error; ambiguous partial files are held for manual
inspection rather than overwritten or automatically deleted.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import os, sqlite3, stat
from .contracts import SpineError, IntegrityFailure
from .path_policy import open_private_root, private_file_at
from .doctor import inspect


def snapshot(db, backup_root: str | Path, name: str, *, max_bytes: int=99_000_000)->dict:
    if not name or not name.endswith('.sqlite') or len(name)>100 or '/' in name or '\\' in name:
        raise SpineError('invalid bounded backup name')
    if type(max_bytes)is not int or not 4096<=max_bytes<=99_000_000:
        raise SpineError('invalid backup ceiling')
    inspect(db,maximum_entries=100_000)
    root=open_private_root(backup_root)
    try:
        fd=private_file_at(root,name,create=True)
        os.close(fd)
        path=f'/proc/self/fd/{root}/{name}'
        output=sqlite3.connect(path,isolation_level=None)
        try:
            with db._lock:
                db._db.backup(output,pages=128,sleep=0.01)
            if output.execute('PRAGMA quick_check').fetchone()!=('ok',):
                raise IntegrityFailure('copied SQLite backup failed quick_check')
        finally:
            output.close()
        fd=private_file_at(root,name)
        try:
            size=os.fstat(fd).st_size
            if size<=0 or size>max_bytes:
                raise SpineError('backup exceeds finite offline artifact ceiling')
            h=sha256()
            while True:
                chunk=os.read(fd,1024*1024)
                if not chunk:break
                h.update(chunk)
            os.fsync(fd)
            result={'status':'private-snapshot-integrity-recorded-not-restore-qualified',
                    'bytes':size,'sha256':h.hexdigest(),'basename':name}
        finally:os.close(fd)
        os.fsync(root)
        return result
    finally:os.close(root)
