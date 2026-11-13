"""Explicitly admitted, model-scoped memory; retrieval is derived, never authority.

A model cannot promote its own generated assertions. Callers must pass
``approved=True`` from an independently authenticated UI/action boundary.
The active index can be rebuilt from this scoped, digest-validated ledger.
"""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
import threading
from ..authority.canonical import ContractViolation,require_small_text,sha256
from ..authority.identity import Actor,require_id
from .sources import Source
from .lexical import LexicalIndex,Hit
from ..persistence.journal import _secure_path


class MemoryStore:
    def __init__(self,path:str|Path=":memory:"):
        name=_secure_path(path)
        self._db=sqlite3.connect(name,isolation_level=None,timeout=10,check_same_thread=False)
        self._lock=threading.RLock()
        if str(path)!=":memory:":
            os.chmod(path,0o600)
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("""CREATE TABLE IF NOT EXISTS ai_memory (
            tenant TEXT NOT NULL,user TEXT NOT NULL,model TEXT NOT NULL,
            source_id TEXT NOT NULL,revision INTEGER NOT NULL,origin TEXT NOT NULL,
            body TEXT NOT NULL,sha256 TEXT NOT NULL,trust TEXT NOT NULL,rights TEXT NOT NULL,
            PRIMARY KEY(tenant,user,model,source_id))""")

    def admit(self,actor:Actor,source:Source,*,approved:bool=False)->None:
        if not approved:
            raise ContractViolation("memory promotion requires independent authorization")
        if source.trust=="model-generated":
            raise ContractViolation("model-generated memory cannot self-promote")
        if (source.owner_tenant,source.owner_user)!=(actor.tenant,actor.user):
            raise ContractViolation("memory scope mismatch")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row=self._db.execute("SELECT revision FROM ai_memory WHERE tenant=? AND user=? AND model=? AND source_id=?",
                    (actor.tenant,actor.user,actor.model_digest,source.source_id)).fetchone()
                if row is not None and source.revision<=row[0]:
                    raise ContractViolation("memory revision conflict")
                self._db.execute("""INSERT INTO ai_memory VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(tenant,user,model,source_id) DO UPDATE SET
                    revision=excluded.revision,origin=excluded.origin,body=excluded.body,
                    sha256=excluded.sha256,trust=excluded.trust,rights=excluded.rights""",
                    (actor.tenant,actor.user,actor.model_digest,source.source_id,
                     source.revision,source.origin,source.body,source.digest,source.trust,source.rights))
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def sources(self,actor:Actor,*,maximum:int=2048)->tuple[Source,...]:
        if type(maximum) is not int or not 1<=maximum<=2048:
            raise ContractViolation("invalid memory read cap")
        with self._lock:
            rows=self._db.execute("SELECT source_id,revision,origin,body,sha256,trust,rights "
                "FROM ai_memory WHERE tenant=? AND user=? AND model=? ORDER BY source_id LIMIT ?",
                (actor.tenant,actor.user,actor.model_digest,maximum+1)).fetchall()
        if len(rows)>maximum:
            raise ContractViolation("memory volume exceeds retrieval cap")
        return tuple(Source(sid,actor.tenant,actor.user,origin,body,digest,trust,rights,revision)
                     for sid,revision,origin,body,digest,trust,rights in rows)

    def search(self,actor:Actor,question:str,*,limit:int=8)->tuple[Hit,...]:
        return LexicalIndex(self.sources(actor)).query(question,tenant=actor.tenant,
                                                       user=actor.user,limit=limit)

    def forget(self,actor:Actor,source_id:str)->bool:
        require_id(source_id,field="source ID")
        with self._lock:
            cursor=self._db.execute("DELETE FROM ai_memory WHERE tenant=? AND user=? AND model=? AND source_id=?",
                (actor.tenant,actor.user,actor.model_digest,source_id))
            return cursor.rowcount==1

    def close(self)->None:
        with self._lock:
            self._db.close()

    def __enter__(self)->"MemoryStore":return self
    def __exit__(self,*_:object)->None:self.close()
