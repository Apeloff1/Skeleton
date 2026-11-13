"""One SQLite authority, WAL durability, transactional custody and integrity checks."""
from __future__ import annotations
import sqlite3,stat,os,time,threading
from pathlib import Path
from contextlib import contextmanager
from .contracts import SpineError,IntegrityFailure
from .schema import DDL,SCHEMA_VERSION
from .path_policy import open_private_root, private_file_at,validate_private_sidecars

class SpineDatabase:
    def __init__(self, root:str|Path, *,readonly:bool=False):
        name='ai-spine.sqlite'
        if type(readonly)is not bool:raise SpineError('invalid read-only flag')
        self._root_fd=open_private_root(root)
        self._closed=False
        self._readonly=readonly
        self._lock=threading.RLock()
        try:
            validate_private_sidecars(self._root_fd,name)
            try:fd=private_file_at(self._root_fd,name)
            except FileNotFoundError:
                if readonly:raise SpineError('read-only doctor will not create a missing database')
                fd=private_file_at(self._root_fd,name,create=True)
            os.close(fd)
            # /proc/self/fd gives SQLite an OS-anchored directory path on Linux.
            # Non-Linux targets are deliberately held pending secure adapter.
            if not Path('/proc/self/fd').is_dir():
                raise SpineError('Linux descriptor-backed SQLite required')
            path=f'/proc/self/fd/{self._root_fd}/{name}'
            connection='file:'+path+'?mode=ro' if readonly else path
            self._db=sqlite3.connect(connection,uri=readonly,isolation_level=None,timeout=10,check_same_thread=False)
            self._db.execute('PRAGMA busy_timeout=10000')
            self._db.execute('PRAGMA foreign_keys=ON')
            self._db.execute('PRAGMA trusted_schema=ON')
            self._db.execute('PRAGMA secure_delete=ON')
            if not readonly:
                journal=self._db.execute('PRAGMA journal_mode=WAL').fetchone()
                if journal!=('wal',):raise SpineError('WAL unavailable')
                self._db.execute('PRAGMA synchronous=FULL')
                for sql in DDL:self._db.execute(sql)
                with self.transaction():
                    self._db.execute("INSERT OR IGNORE INTO controls VALUES ('schema_version',?)",(str(SCHEMA_VERSION),))
            version=self._db.execute("SELECT value FROM controls WHERE control='schema_version'").fetchone()
            if version!=(str(SCHEMA_VERSION),):raise SpineError('unsupported database schema version')
            self.inspect()
        except BaseException:
            if hasattr(self,'_db'):self._db.close()
            os.close(self._root_fd);raise

    def inspect(self):
        if self._closed:raise SpineError('database closed')
        validate_private_sidecars(self._root_fd,'ai-spine.sqlite')
        with self._lock:
            if self._db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise IntegrityFailure('foreign keys disabled')
            if self._db.execute('PRAGMA quick_check').fetchone()!=('ok',):raise IntegrityFailure('SQLite quick_check failed')
            if self._db.execute('PRAGMA foreign_key_check').fetchone():raise IntegrityFailure('foreign key mismatch')

    @contextmanager
    def transaction(self):
        if self._readonly:raise SpineError('read-only doctor cannot begin write transaction')
        with self._lock:
            self._db.execute('BEGIN IMMEDIATE')
            try:
                yield self._db
                self._db.execute('COMMIT')
            except BaseException:
                self._db.execute('ROLLBACK')
                raise

    @contextmanager
    def snapshot(self):
        with self._lock:
            self._db.execute('BEGIN')
            try:
                yield self._db
            finally:
                self._db.execute('ROLLBACK')

    def close(self):
        if not self._closed:
            self._closed=True
            self._db.close();os.close(self._root_fd)
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
