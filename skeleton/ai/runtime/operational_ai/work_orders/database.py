"""Private descriptor-rooted SQLite WAL storage, independent of chat authority.

Linux only; no silent unsafe Windows file-path fallback. The existing
ExecutionSpine SQLite database remains the owner of actual generated output.
"""
from __future__ import annotations
import os
import sqlite3
import threading
from contextlib import contextmanager
from .contracts import refuse
from .schema import DDL
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.path_policy import (
    open_private_root,private_file_at,validate_private_sidecars)
_NAME="ai-work-orders-v2.sqlite"
class WorkDatabase:
    def __init__(self,state_dir,*,readonly=False):
        if type(readonly) is not bool:refuse("explicit readonly policy required")
        self._root=open_private_root(state_dir)
        self._lock=threading.RLock()
        self._closed=False;self._readonly=readonly
        try:
            validate_private_sidecars(self._root,_NAME)
            try:fd=private_file_at(self._root,_NAME)
            except FileNotFoundError:
                if readonly:refuse("doctor cannot create a missing database")
                fd=private_file_at(self._root,_NAME,create=True)
            os.close(fd)
            if not os.path.isdir("/proc/self/fd"):
                refuse("Linux anchored proc filesystem required")
            path=f"/proc/self/fd/{self._root}/{_NAME}"
            self.conn=sqlite3.connect("file:"+path+"?mode=ro" if readonly else path,
                         uri=readonly,isolation_level=None,timeout=10,check_same_thread=False)
            self.conn.execute("PRAGMA busy_timeout=10000")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA trusted_schema=OFF")
            self.conn.execute("PRAGMA secure_delete=ON")
            if not readonly:
                if self.conn.execute("PRAGMA journal_mode=WAL").fetchone()!=("wal",):
                    refuse("write-ahead logging is unavailable")
                self.conn.execute("PRAGMA synchronous=FULL")
                for sql in DDL:self.conn.execute(sql)
                with self.transaction() as c:
                    c.execute("INSERT OR IGNORE INTO controls VALUES ('version','2')")
            if self.conn.execute("SELECT value FROM controls WHERE key='version'").fetchone()!=("2",):
                refuse("unsupported work-order schema version")
            self.inspect()
        except BaseException:
            if hasattr(self,"conn"):self.conn.close()
            os.close(self._root)
            raise

    def inspect(self):
        if self._closed:refuse("closed state database")
        validate_private_sidecars(self._root,_NAME)
        with self._lock:
            if self.conn.execute("PRAGMA foreign_keys").fetchone()!=(1,):
                refuse("foreign keys disabled")
            if self.conn.execute("PRAGMA quick_check").fetchone()!=("ok",):
                refuse("work-order storage integrity failure")
            if self.conn.execute("PRAGMA foreign_key_check").fetchone():
                refuse("work-order referential integrity failure")
        return {"state":"sqlite-integrity-observed","private_state":True,
                "native_e2e_tested":False}

    @contextmanager
    def transaction(self):
        if self._readonly:refuse("readonly state cannot write")
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    @contextmanager
    def snapshot(self):
        with self._lock:
            self.conn.execute("BEGIN")
            try:yield self.conn
            finally:self.conn.execute("ROLLBACK")

    def close(self):
        if not self._closed:
            self._closed=True
            self.conn.close()
            os.close(self._root)
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
