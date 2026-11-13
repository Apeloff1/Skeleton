"""Tenant-scoped SQLite plaintext-free metadata catalog with explicit source deletion.

Content is not stored here: only source digests, sizes, consent expiry and
tombstones. A private operator-owned content store remains responsible for
encrypted payload bytes, key lifecycle and actual deletion confirmation.
"""
from __future__ import annotations
import sqlite3
import threading
from .contracts import Scope,identifier,sha,integer,refuse,hash_bytes
_SCHEMA=(
"""CREATE TABLE IF NOT EXISTS memories(
 tenant TEXT NOT NULL,subject TEXT NOT NULL,source_id TEXT NOT NULL,
 source_sha TEXT NOT NULL,length INTEGER NOT NULL,consent_until_ns INTEGER NOT NULL,
 state TEXT NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(tenant,subject,source_id),
 CHECK(state IN ('active','tombstoned'))) STRICT""",
"""CREATE TABLE IF NOT EXISTS provenance(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,tenant TEXT NOT NULL,
 subject TEXT NOT NULL,source_id TEXT NOT NULL,action TEXT NOT NULL,
 source_sha TEXT NOT NULL,created_ns INTEGER NOT NULL) STRICT"""
)
class MemoryCatalog:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=10,isolation_level=None,check_same_thread=False)
        self.lock=threading.RLock()
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        for ddl in _SCHEMA:self.db.execute(ddl)
    def close(self):self.db.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
    def _tx(self,fn):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                result=fn(self.db)
                self.db.execute("COMMIT")
                return result
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
    def remember(self,scope,source_id,source_sha,*,length,now_ns,consent_until_ns):
        if type(scope) is not Scope:refuse("memory scope required")
        identifier(source_id);sha(source_sha)
        integer(length,minimum=1,maximum=2**32)
        integer(now_ns);integer(consent_until_ns,minimum=now_ns+1)
        if consent_until_ns-now_ns>365*24*3600*10**9:
            refuse("memory consent retention unbounded")
        def insert(db):
            old=db.execute("""SELECT state,revision FROM memories WHERE
                 tenant=? AND subject=? AND source_id=?""",
                 (scope.tenant,scope.subject,source_id)).fetchone()
            if old is not None:refuse("source ID already recorded or tombstoned")
            db.execute("INSERT INTO memories VALUES (?,?,?,?,?,?,?,?)",
                      (scope.tenant,scope.subject,source_id,source_sha,length,
                       consent_until_ns,"active",1))
            db.execute("INSERT INTO provenance(tenant,subject,source_id,action,source_sha,created_ns) VALUES (?,?,?,?,?,?)",
                      (scope.tenant,scope.subject,source_id,"created",source_sha,now_ns))
            return {"source_id":source_id,"revision":1,"source_sha256":source_sha,
                    "payload_bytes_stored_here":0}
        return self._tx(insert)
    def list(self,scope,*,now_ns,limit=100):
        if type(scope) is not Scope:refuse("memory scope required")
        integer(now_ns);integer(limit,minimum=1,maximum=1000)
        with self.lock:
            rows=self.db.execute("""SELECT source_id,source_sha,length,revision
                 FROM memories WHERE tenant=? AND subject=? AND state='active'
                 AND consent_until_ns>? ORDER BY source_id LIMIT ?""",
                 (scope.tenant,scope.subject,now_ns,limit)).fetchall()
            return tuple({"source_id":i,"sha256":h,"length":n,"revision":r}
                         for i,h,n,r in rows)
    def tombstone(self,scope,source_id,*,expected_revision,now_ns):
        if type(scope) is not Scope:refuse("memory principal required")
        identifier(source_id);integer(expected_revision,minimum=1);integer(now_ns)
        def revoke(db):
            old=db.execute("""SELECT source_sha FROM memories WHERE tenant=?
                    AND subject=? AND source_id=? AND state='active'
                    AND revision=?""",
                    (scope.tenant,scope.subject,source_id,expected_revision)).fetchone()
            if old is None:refuse("source missing or tombstone CAS failed")
            if db.execute("""UPDATE memories SET state='tombstoned',revision=revision+1
                    WHERE tenant=? AND subject=? AND source_id=? AND revision=?""",
                    (scope.tenant,scope.subject,source_id,expected_revision)).rowcount!=1:
                refuse("memory tombstone revision conflict")
            db.execute("INSERT INTO provenance(tenant,subject,source_id,action,source_sha,created_ns) VALUES (?,?,?,?,?,?)",
                      (scope.tenant,scope.subject,source_id,"tombstoned",old[0],now_ns))
            return {"source_id":source_id,"tombstoned":True,
                    "physical_payload_erasure_proved":False}
        return self._tx(revoke)
