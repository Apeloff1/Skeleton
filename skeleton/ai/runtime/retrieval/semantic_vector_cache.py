"""Disposable, model/scope/content-bound derived vector cache in existing SQLite.

It owns no source authority. Checksums detect accidental corruption; an
adversarial owner-controlled database is not authenticated by this cache.
"""
from __future__ import annotations

import hashlib
import sqlite3
import struct
import time
from .learned_embeddings import SpanEmbedding


class DerivedVectorCache:
    def __init__(self,db,lock,scope,*,dimension,segments,max_bytes=128*1024**2):
        if not isinstance(db,sqlite3.Connection) or not isinstance(scope,str) or len(scope)!=64:
            raise ValueError("canonical scoped SQLite cache required")
        if type(dimension) is not int or not 2<=dimension<=4096 or type(segments) is not int or not 1<=segments<=16:
            raise ValueError("cache vector geometry invalid")
        if type(max_bytes) is not int or not 1024<=max_bytes<=2**31:
            raise ValueError("cache byte ceiling invalid")
        self.db,self.lock,self.scope=db,lock,scope
        self.dimension,self.segments,self.max_bytes=dimension,segments,max_bytes
        with lock:
            db.execute("""CREATE TABLE IF NOT EXISTS offline_semantic_vectors (
                scope TEXT NOT NULL, space TEXT NOT NULL, span TEXT NOT NULL,
                payload BLOB NOT NULL, digest TEXT NOT NULL, touched INTEGER NOT NULL,
                PRIMARY KEY(scope,space,span))""")
            db.execute("""CREATE INDEX IF NOT EXISTS offline_semantic_vectors_lru
                ON offline_semantic_vectors(scope,touched)""")

    def _encode(self,vector):
        if not isinstance(vector,SpanEmbedding) or len(vector.dense)!=self.dimension or not 1<=len(vector.segments)<=self.segments or any(len(x)!=self.dimension for x in vector.segments):
            raise ValueError("cache feature geometry mismatch")
        flat=tuple(vector.dense)+tuple(x for part in vector.segments for x in part)
        return struct.pack("<I",len(vector.segments))+struct.pack("<"+"f"*len(flat),*flat)

    def _decode(self,raw):
        if not isinstance(raw,bytes) or len(raw)<4:
            raise ValueError("cache vector payload invalid")
        n=struct.unpack_from("<I",raw)[0]
        count=(n+1)*self.dimension
        if not 1<=n<=self.segments or len(raw)!=4+4*count:
            raise ValueError("cache vector length mismatch")
        flat=struct.unpack_from("<"+"f"*count,raw,4)
        return SpanEmbedding(flat[:self.dimension],tuple(flat[i*self.dimension:(i+1)*self.dimension] for i in range(1,n+1)))

    def _digest(self,space,span,payload):
        return hashlib.sha256((self.scope+":"+space+":"+span+":").encode()+payload).hexdigest()

    def get(self,space,span):
        with self.lock:
            found=self.db.execute("""SELECT payload,digest FROM offline_semantic_vectors
                WHERE scope=? AND space=? AND span=?""",(self.scope,space,span)).fetchone()
        if found is None:return None
        payload,pin=found
        if self._digest(space,span,payload)!=pin:
            raise ValueError("derived semantic cache checksum mismatch")
        return self._decode(payload)

    def put(self,space,span,vector):
        payload=self._encode(vector)
        if len(payload)>self.max_bytes:
            raise MemoryError("single semantic cache vector exceeds quota")
        with self.lock:
            # The enclosing canonical store owns its write transaction.
            # Savepoints avoid committing unrelated application state.
            self.db.execute("SAVEPOINT semantic_vector_write")
            try:
                total=self.db.execute("SELECT COALESCE(SUM(length(payload)),0) FROM offline_semantic_vectors WHERE scope=?",(self.scope,)).fetchone()[0]
                old=self.db.execute("SELECT length(payload) FROM offline_semantic_vectors WHERE scope=? AND space=? AND span=?",(self.scope,space,span)).fetchone()
                total-=old[0] if old else 0
                while total+len(payload)>self.max_bytes:
                    victim=self.db.execute("""SELECT space,span,length(payload) FROM offline_semantic_vectors
                        WHERE scope=? AND NOT(space=? AND span=?) ORDER BY touched,space,span LIMIT 1""",(self.scope,space,span)).fetchone()
                    if victim is None:raise MemoryError("semantic cache quota cannot be met")
                    self.db.execute("DELETE FROM offline_semantic_vectors WHERE scope=? AND space=? AND span=?",(self.scope,victim[0],victim[1]))
                    total-=victim[2]
                self.db.execute("""INSERT INTO offline_semantic_vectors VALUES(?,?,?,?,?,?)
                    ON CONFLICT(scope,space,span) DO UPDATE SET payload=excluded.payload,
                    digest=excluded.digest,touched=excluded.touched""",(self.scope,space,span,payload,self._digest(space,span,payload),time.time_ns()))
                self.db.execute("RELEASE semantic_vector_write")
            except BaseException:
                self.db.execute("ROLLBACK TO semantic_vector_write")
                self.db.execute("RELEASE semantic_vector_write")
                raise

    def invalidate(self):
        with self.lock:
            self.db.execute("DELETE FROM offline_semantic_vectors WHERE scope=?",(self.scope,))
