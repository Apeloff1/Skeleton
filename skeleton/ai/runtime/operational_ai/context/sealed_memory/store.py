"""Encrypted SQLite offline memory; scoped source provenance, no plaintext disk index.

Search decrypts a bounded caller-specific candidate set into RAM, then uses
the existing lexical matching implementation. All writes are explicit caller-
approved, and the model is never the authority promoting its own output.
"""
from __future__ import annotations
import os,sqlite3,threading,json
from pathlib import Path
from ..sources import Source
from ..lexical import LexicalIndex,Hit
from ...authority.identity import Actor,require_id
from ...authority.canonical import ContractViolation,sha256
from ...persistence.journal import _secure_path
from .keys import KeyMaterial,MemoryKeyError
from .codec import aad,seal,open_sealed

class SealedMemoryStore:
    def __init__(self,path:str|Path,keys:KeyMaterial,*,max_sources:int=2048):
        if not isinstance(keys,KeyMaterial):raise MemoryKeyError('encryption master key required')
        if type(max_sources) is not int or not 1<=max_sources<=10_000:
            raise MemoryKeyError('invalid memory volume ceiling')
        name=_secure_path(path)
        self.keys=keys;self.maximum=max_sources
        self._db=sqlite3.connect(name,isolation_level=None,timeout=10,check_same_thread=False)
        self._lock=threading.RLock()
        self._db.execute('PRAGMA foreign_keys=ON')
        self._db.execute('PRAGMA synchronous=FULL')
        if str(path)!=':memory:':
            os.chmod(path,0o600)
            self._db.execute('PRAGMA journal_mode=WAL')
        self._db.execute('''CREATE TABLE IF NOT EXISTS sealed_ai_memory (
           tenant TEXT NOT NULL,user TEXT NOT NULL,model_sha TEXT NOT NULL,
           source_id TEXT NOT NULL,revision INTEGER NOT NULL,source_sha TEXT NOT NULL,
           epoch INTEGER NOT NULL,nonce BLOB NOT NULL,ciphertext BLOB NOT NULL,
           PRIMARY KEY(tenant,user,model_sha,source_id))''')

    def admit(self,actor:Actor,source:Source,*,approved:bool=False)->None:
        if approved is not True:raise MemoryKeyError('independent memory promotion required')
        if source.trust=='model-generated':raise MemoryKeyError('self-promoted model memory denied')
        if (source.owner_tenant,source.owner_user)!=(actor.tenant,actor.user):
            raise MemoryKeyError('owner mismatch')
        try:
            record=json.dumps({key:getattr(source,key) for key in source.__dataclass_fields__},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        except Exception as exc:raise MemoryKeyError('invalid memory content') from exc
        source_sha=source.digest
        key=self.keys.derive(actor.tenant,actor.user,actor.model_digest)
        associated=aad(actor.tenant,actor.user,actor.model_digest,source.source_id,
                       source.revision,source_sha,self.keys.epoch)
        nonce,encrypted=seal(record,key,associated)
        with self._lock:
            self._db.execute('BEGIN IMMEDIATE')
            try:
                existing=self._db.execute('SELECT revision FROM sealed_ai_memory WHERE tenant=? AND user=? AND model_sha=? AND source_id=?',
                    (actor.tenant,actor.user,actor.model_digest,source.source_id)).fetchone()
                if existing and source.revision<=existing[0]:raise MemoryKeyError('memory revision conflict')
                count=self._db.execute('SELECT COUNT(*) FROM sealed_ai_memory WHERE tenant=? AND user=? AND model_sha=?',
                    (actor.tenant,actor.user,actor.model_digest)).fetchone()[0]
                if not existing and count>=self.maximum:raise MemoryKeyError('sealed memory at finite capacity')
                self._db.execute('''INSERT INTO sealed_ai_memory VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(tenant,user,model_sha,source_id) DO UPDATE SET
                    revision=excluded.revision,source_sha=excluded.source_sha,epoch=excluded.epoch,
                    nonce=excluded.nonce,ciphertext=excluded.ciphertext''',
                    (actor.tenant,actor.user,actor.model_digest,source.source_id,
                     source.revision,source_sha,self.keys.epoch,nonce,encrypted))
                self._db.execute('COMMIT')
            except BaseException:
                self._db.execute('ROLLBACK');raise

    def sources(self,actor:Actor,*,maximum:int=2048)->tuple[Source,...]:
        if type(maximum) is not int or not 1<=maximum<=self.maximum:
            raise MemoryKeyError('invalid bounded memory query')
        with self._lock:
            rows=self._db.execute('''SELECT source_id,revision,source_sha,epoch,nonce,ciphertext
                FROM sealed_ai_memory WHERE tenant=? AND user=? AND model_sha=? ORDER BY source_id LIMIT ?''',
                (actor.tenant,actor.user,actor.model_digest,maximum+1)).fetchall()
        if len(rows)>maximum:raise MemoryKeyError('candidate memory volume exceeds admission limit')
        out=[];key=self.keys.derive(actor.tenant,actor.user,actor.model_digest)
        for source_id,revision,source_sha,epoch,nonce,ciphertext in rows:
            if epoch!=self.keys.epoch:
                raise MemoryKeyError('key rotation needed before reading old epoch')
            associated=aad(actor.tenant,actor.user,actor.model_digest,source_id,revision,source_sha,epoch)
            raw=open_sealed(nonce,ciphertext,key,associated)
            try:record=json.loads(raw.decode())
            except (UnicodeError,ValueError) as exc:raise MemoryKeyError('decrypted memory corrupted') from exc
            source=Source(**record)
            if source.digest!=source_sha or source.source_id!=source_id or source.revision!=revision:
                raise MemoryKeyError('source identity changed inside sealed memory')
            out.append(source)
        return tuple(out)

    def search(self,actor:Actor,question:str,*,limit:int=8)->tuple[Hit,...]:
        return LexicalIndex(self.sources(actor,maximum=self.maximum)).query(question,
                 tenant=actor.tenant,user=actor.user,limit=limit)

    def forget(self,actor:Actor,source_id:str)->bool:
        require_id(source_id,field='source ID')
        with self._lock:
            cursor=self._db.execute('DELETE FROM sealed_ai_memory WHERE tenant=? AND user=? AND model_sha=? AND source_id=?',
                       (actor.tenant,actor.user,actor.model_digest,source_id))
            return cursor.rowcount==1

    def close(self)->None:
        with self._lock:self._db.close()
    def __enter__(self)->'SealedMemoryStore':return self
    def __exit__(self,*_:object)->None:self.close()
