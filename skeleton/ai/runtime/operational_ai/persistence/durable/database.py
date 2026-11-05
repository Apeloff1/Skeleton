"""Single-process SQLite custody, explicit transaction boundaries and secure files.

This database is a separately opted-in operation plane; it never silently
replaces the canonical conversation authority or imports secrets from env.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
import os,sqlite3,threading,stat

class DurableError(RuntimeError):pass

class DurableDatabase:
    def __init__(self,path:str|Path=':memory:'):
        self.path=str(path)
        self._lock=threading.RLock()
        if self.path!=':memory:':
            p=Path(path).absolute()
            if p.is_symlink() or p.parent.is_symlink() or not p.parent.is_dir():
                raise DurableError('database path must have existing, non-symlink directory')
            if p.exists():
                s=p.lstat()
                if not stat.S_ISREG(s.st_mode) or s.st_mode&0o077:
                    raise DurableError('private operation database requires mode 0600')
            else:
                fd=os.open(p,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                os.close(fd)
        self._db=sqlite3.connect(self.path,timeout=15,check_same_thread=False,isolation_level=None)
        self._db.execute('PRAGMA foreign_keys=ON')
        self._db.execute('PRAGMA busy_timeout=15000')
        self._db.execute('PRAGMA synchronous=FULL')
        if self.path!=':memory:':
            self._db.execute('PRAGMA journal_mode=WAL')
        self._db.execute('''CREATE TABLE IF NOT EXISTS ai_operation (
            tenant TEXT NOT NULL, owner TEXT NOT NULL, operation TEXT NOT NULL,
            state TEXT NOT NULL, version INTEGER NOT NULL, lease_fence INTEGER NOT NULL DEFAULT 0,
            request_sha TEXT NOT NULL, payload BLOB NOT NULL, result BLOB,
            created_ns INTEGER NOT NULL, updated_ns INTEGER NOT NULL,
            PRIMARY KEY (tenant,owner,operation))''')
        self._db.execute('''CREATE TABLE IF NOT EXISTS ai_operation_events (
            tenant TEXT NOT NULL, owner TEXT NOT NULL, operation TEXT NOT NULL,
            seq INTEGER NOT NULL, event_id TEXT NOT NULL, name TEXT NOT NULL,
            payload BLOB NOT NULL, prior_sha TEXT NOT NULL, event_sha TEXT NOT NULL,
            PRIMARY KEY (tenant,owner,operation,seq),
            UNIQUE (tenant,owner,operation,event_id),
            FOREIGN KEY (tenant,owner,operation) REFERENCES ai_operation ON DELETE CASCADE)''')
        self._db.execute('''CREATE TABLE IF NOT EXISTS ai_operation_outbox (
            tenant TEXT NOT NULL, owner TEXT NOT NULL, operation TEXT NOT NULL,
            message_id TEXT NOT NULL, destination TEXT NOT NULL, payload BLOB NOT NULL,
            state TEXT NOT NULL, attempts INTEGER NOT NULL, next_attempt_ns INTEGER NOT NULL,
            fence INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (tenant,owner,operation,message_id),
            FOREIGN KEY (tenant,owner,operation) REFERENCES ai_operation ON DELETE CASCADE)''')
        self._db.execute('''CREATE TABLE IF NOT EXISTS ai_operation_inbox (
            consumer TEXT NOT NULL, message_id TEXT NOT NULL, message_sha TEXT NOT NULL,
            received_ns INTEGER NOT NULL, PRIMARY KEY (consumer,message_id))''')
        self._db.execute('''CREATE TABLE IF NOT EXISTS ai_leases (
            lease_key TEXT PRIMARY KEY, owner TEXT NOT NULL, fence INTEGER NOT NULL,
            expires_ns INTEGER NOT NULL)''')
        self._db.execute('''CREATE TABLE IF NOT EXISTS ai_requests (
            scope TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
            receipt BLOB NOT NULL, PRIMARY KEY (scope,request_id))''')
        self._db.execute('''CREATE TABLE IF NOT EXISTS ai_snapshots (
            tenant TEXT NOT NULL, owner TEXT NOT NULL, operation TEXT NOT NULL,
            seq INTEGER NOT NULL, payload BLOB NOT NULL, terminal_sha TEXT NOT NULL,
            PRIMARY KEY (tenant,owner,operation,seq),
            FOREIGN KEY (tenant,owner,operation) REFERENCES ai_operation ON DELETE CASCADE)''')
        self._closed=False

    @contextmanager
    def transaction(self)->Iterator[sqlite3.Connection]:
        with self._lock:
            if self._closed:raise DurableError('operation database closed')
            self._db.execute('BEGIN IMMEDIATE')
            try:
                yield self._db
                self._db.execute('COMMIT')
            except BaseException:
                self._db.execute('ROLLBACK')
                raise

    def query(self,sql:str,args:tuple=())->list[tuple]:
        if not sql.lstrip().upper().startswith('SELECT'):
            raise DurableError('read-only query API')
        with self._lock:
            if self._closed:raise DurableError('operation database closed')
            return self._db.execute(sql,args).fetchall()

    def check(self)->dict[str,object]:
        with self._lock:
            result=self._db.execute('PRAGMA integrity_check').fetchone()
            return {'status':'ok' if result==('ok',) else 'corrupt',
                    'sqlite_integrity':result[0] if result else 'unknown',
                    'foreign_keys':self._db.execute('PRAGMA foreign_keys').fetchone()[0]}

    def close(self)->None:
        with self._lock:
            if not self._closed:
                self._db.close();self._closed=True

    def __enter__(self)->'DurableDatabase':return self
    def __exit__(self,*_:object)->None:self.close()
