"""Sharded versioned game datasets for MMO-scale public static exports.

Accept operator-supplied JSON Lines; do not fetch authenticated APIs, execute
tools, or infer that a local import is verified source truth. Each version is
immutable after a complete page-chain seal. Query only live sealed versions.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from contextlib import contextmanager

from core.dragon_game_corpus import GameCorpus,_id,key,clean,digest,CatalogueHeld
from core.dragon_hoarder_bulk import owner_key
from core.dragon_corpus_runtime import _path

MAX_PAGE=2*1024**2
MAX_RECORD=64*1024
MAX_ROWS=512
MAX_VERSION_ROWS=100_000_000
MAX_VERSIONS=100_000
MAX_GRANT=30*86400
ZERO="0"*64
SHARDS=256
DENY_KEYS={"password","password_hash","access_token","refresh_token","auth_token","authorization",
           "client_secret","api_key","secret_key","email","private_key","session_cookie","cookie",
           "mail_body","wallet_journal","private_message"}
SCHEMA="""
CREATE TABLE IF NOT EXISTS dataset_versions(
 owner TEXT NOT NULL,game TEXT NOT NULL,id TEXT NOT NULL,dataset TEXT NOT NULL,source TEXT NOT NULL,
 observation_digest TEXT NOT NULL,label TEXT NOT NULL,expected_rows INTEGER NOT NULL,expected_chain TEXT NOT NULL,
 rows INTEGER NOT NULL DEFAULT 0,next_page INTEGER NOT NULL DEFAULT 0,chain TEXT NOT NULL,
 created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('building','sealed','revoked','erased')),
 PRIMARY KEY(owner,game,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS dataset_version_lookup ON dataset_versions(owner,game,dataset,created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS dataset_expiry ON dataset_versions(state,expires_at,owner,game,id);
CREATE TABLE IF NOT EXISTS dataset_pages(
 owner TEXT NOT NULL,game TEXT NOT NULL,version TEXT NOT NULL,ordinal INTEGER NOT NULL,
 page_hash TEXT NOT NULL,rows INTEGER NOT NULL,chain TEXT NOT NULL,
 PRIMARY KEY(owner,game,version,ordinal),
 FOREIGN KEY(owner,game,version) REFERENCES dataset_versions(owner,game,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS dataset_records(
 owner TEXT NOT NULL,game TEXT NOT NULL,version TEXT NOT NULL,record_key TEXT NOT NULL,
 data_json TEXT NOT NULL,row_hash TEXT NOT NULL,fts_row INTEGER NOT NULL,
 PRIMARY KEY(owner,game,version,record_key),UNIQUE(fts_row),
 FOREIGN KEY(owner,game,version) REFERENCES dataset_versions(owner,game,id)
) WITHOUT ROWID;
CREATE VIRTUAL TABLE IF NOT EXISTS dataset_fts USING fts5(
 owner,game,version,record_key UNINDEXED,search_text,tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS dataset_edges(
 owner TEXT NOT NULL,game TEXT NOT NULL,version TEXT NOT NULL,record_key TEXT NOT NULL,
 relation TEXT NOT NULL,target TEXT NOT NULL,PRIMARY KEY(owner,game,version,record_key,relation,target),
 FOREIGN KEY(owner,game,version,record_key) REFERENCES dataset_records(owner,game,version,record_key)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS dataset_reverse_edge ON dataset_edges(owner,game,version,target,relation,record_key);
"""


def chain_step(previous,page_hash,ordinal,rows):
    return hashlib.sha256(bytes.fromhex(_id(previous))+bytes.fromhex(_id(page_hash))+
                          ordinal.to_bytes(8,"big")+rows.to_bytes(8,"big")).hexdigest()


def _pairs(items):
    out={}
    for k,v in items:
        if k in out:raise ValueError("duplicate JSON field")
        out[k]=v
    return out


def _scalar(value):
    if type(value) is int:
        if not 0<=value<2**63:raise ValueError("record id integer bound")
        return str(value)
    return key(value)


def _projection(value,*,depth=0,out=None,budget=None):
    if out is None:out=[]
    if budget is None:budget=[0]
    budget[0]+=1
    if depth>12 or budget[0]>4096:raise ValueError("dataset structural bounds")
    if isinstance(value,dict):
        for k,v in value.items():
            if not isinstance(k,str) or len(k)>128 or k.casefold() in DENY_KEYS:
                raise ValueError("private or invalid dataset key")
            if len(out)<128:out.append(k[:80])
            _projection(v,depth=depth+1,out=out,budget=budget)
    elif isinstance(value,list):
        for v in value:_projection(v,depth=depth+1,out=out,budget=budget)
    elif value is None or type(value) in (bool,int,float):
        if len(out)<128:out.append(str(value)[:80])
    elif isinstance(value,str):
        if len(out)<128:out.append(value[:256])
    else:raise ValueError("unsupported JSON value")
    return " ".join(out)[:16000]


def parse_page(raw):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_PAGE:
        raise ValueError("dataset page byte bound")
    lines=raw.splitlines()
    if not 1<=len(lines)<=MAX_ROWS or any(not line.strip() or len(line)>MAX_RECORD for line in lines):
        raise ValueError("dataset JSONL row bound")
    parsed=[]
    seen=set()
    for line in lines:
        value=json.loads(line,object_pairs_hook=_pairs,
                parse_constant=lambda _:(_ for _ in ()).throw(ValueError("nonfinite dataset number")))
        if not isinstance(value,dict) or "_key" not in value:
            raise ValueError("explicit static dataset _key required")
        record=_scalar(value["_key"])
        if record in seen:raise ValueError("duplicate record in page")
        seen.add(record)
        search=_projection(value)
        edges=[]
        relations=value.get("_relations",[])
        if not isinstance(relations,list) or len(relations)>64:raise ValueError("relation limit")
        for item in relations:
            if not isinstance(item,dict) or set(item)!={"kind","target"}:raise ValueError("relation shape")
            edges.append((key(item["kind"]),_scalar(item["target"])))
        normalized=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
        parsed.append((record,normalized,hashlib.sha256(normalized.encode()).hexdigest(),search,sorted(set(edges))))
    return parsed


def _root():
    value=os.getenv("SKL_DRAGON_DATASET_ROOT","").strip()
    p=Path(value)
    if not value or not p.is_absolute() or p.resolve(strict=True)!=p or not p.is_dir():
        raise CatalogueHeld("private dataset directory required")
    st=p.stat()
    if os.name=="posix" and (st.st_uid!=os.getuid() or st.st_mode&0o077):
        raise CatalogueHeld("dataset directory must be private")
    return p


class DatasetShard:
    def __init__(self,scope,game,*,create=False,root=None):
        self.scope=scope
        self.owner=owner_key(scope);self.game=_id(game)
        self.root=Path(root) if root is not None else _root()
        if self.root.resolve(strict=True)!=self.root or not self.root.is_dir():
            raise CatalogueHeld("dataset directory identity")
        st=self.root.stat()
        if os.name=="posix" and (st.st_uid!=os.getuid() or st.st_mode&0o077):
            raise CatalogueHeld("private dataset directory required")
        shard=hashlib.sha256((self.owner+self.game).encode()).hexdigest()[:2]
        self.path=self.root/("game-data-"+shard+".sqlite3")
        self.root_id=(st.st_dev,st.st_ino)
        if not self.path.exists():
            if not create:raise LookupError("dataset shard unavailable")
            try:fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            except FileExistsError:pass
            else:os.close(fd)
        st=self.path.stat()
        self.file_id=(st.st_dev,st.st_ino)

    @contextmanager
    def _db(self):
        root=self.root.stat()
        st=self.path.stat()
        if self.root.resolve(strict=True)!=self.root or (root.st_dev,root.st_ino)!=self.root_id or self.path.is_symlink() or (st.st_dev,st.st_ino)!=self.file_id:
            raise CatalogueHeld("dataset shard identity changed")
        if os.name=="posix" and (st.st_uid!=os.getuid() or st.st_mode&0o077 or st.st_nlink!=1):
            raise CatalogueHeld("dataset shard permissions")
        for suffix in ("-wal","-shm"):
            p=Path(str(self.path)+suffix)
            if p.is_symlink() or p.exists() and not p.is_file():raise CatalogueHeld("database sidecar")
        db=sqlite3.connect(self.path.as_uri()+"?mode=rw",uri=True,isolation_level=None,timeout=5)
        db.row_factory=sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA busy_timeout=5000")
            db.executescript(SCHEMA)
            yield db
        finally:db.close()

    def _get(self,db,version,states=("sealed",),live=True):
        row=db.execute("SELECT * FROM dataset_versions WHERE owner=? AND game=? AND id=?",
            (self.owner,self.game,_id(version))).fetchone()
        if not row or row["state"] not in states or live and row["expires_at"]<=time.time():
            raise LookupError("dataset version unavailable")
        return row

    @staticmethod
    def _public(row):
        return {k:row[k] for k in ("id","game","dataset","source","label","expected_rows","rows","next_page","chain","state","created_at","expires_at")}

    def begin(self,*,dataset,source,observation_digest,label,expected_rows,expected_chain,grant_seconds,rights_acknowledged,corpus=None):
        if rights_acknowledged is not True or type(expected_rows) is not int or not 1<=expected_rows<=MAX_VERSION_ROWS:
            raise ValueError("dataset admission")
        if type(grant_seconds) is not int or not 300<=grant_seconds<=MAX_GRANT:raise ValueError("dataset grant duration")
        dataset=key(dataset);source,observation_digest,expected_chain=map(_id,(source,observation_digest,expected_chain))
        label=clean(label,128)
        (corpus or GameCorpus(_path())).capture_plan(self.scope,self.game,source,observation_digest)
        version=digest([self.owner,self.game,dataset,source,label,expected_rows,expected_chain])
        now=int(time.time())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old=db.execute("SELECT * FROM dataset_versions WHERE owner=? AND game=? AND id=?",
                    (self.owner,self.game,version)).fetchone()
                if old:
                    if old["observation_digest"]!=observation_digest or old["state"] not in {"building","sealed"} or old["expires_at"]<=now:
                        raise CatalogueHeld("dataset operation not replayable")
                else:
                    count=db.execute("SELECT COUNT(*) FROM dataset_versions WHERE owner=? AND game=?",(self.owner,self.game)).fetchone()[0]
                    if count>=MAX_VERSIONS:raise CatalogueHeld("dataset version capacity")
                    db.execute("""INSERT INTO dataset_versions(owner,game,id,dataset,source,observation_digest,label,expected_rows,expected_chain,chain,created_at,expires_at,state)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'building')""",
                        (self.owner,self.game,version,dataset,source,observation_digest,label,expected_rows,expected_chain,ZERO,now,now+grant_seconds))
                row=self._get(db,version,("building","sealed"))
                db.execute("COMMIT")
                return {**self._public(row),"source_verified":False,"training_allowed":False}
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def append(self,version,ordinal,raw):
        if type(ordinal) is not int or not 0<=ordinal<MAX_VERSION_ROWS:raise ValueError("page ordinal")
        records=parse_page(raw)
        page_hash=hashlib.sha256(raw).hexdigest()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=self._get(db,version,("building","sealed"))
                old=db.execute("SELECT page_hash,rows,chain FROM dataset_pages WHERE owner=? AND game=? AND version=? AND ordinal=?",
                    (self.owner,self.game,version,ordinal)).fetchone()
                if old:
                    if old["page_hash"]!=page_hash:raise CatalogueHeld("dataset page identity differs")
                    db.execute("COMMIT")
                    return {**dict(old),"replayed":True}
                if row["state"]!="building" or ordinal!=row["next_page"] or row["rows"]+len(records)>row["expected_rows"]:
                    raise CatalogueHeld("dataset sequence or row bounds")
                for record,body,h,search,edges in records:
                    receipt=db.execute("INSERT INTO dataset_fts(owner,game,version,record_key,search_text) VALUES(?,?,?,?,?)",
                        (self.owner,self.game,version,record,search))
                    db.execute("INSERT INTO dataset_records VALUES(?,?,?,?,?,?,?)",
                        (self.owner,self.game,version,record,body,h,receipt.lastrowid))
                    db.executemany("INSERT INTO dataset_edges VALUES(?,?,?,?,?,?)",
                        [(self.owner,self.game,version,record,k,target) for k,target in edges])
                chain=chain_step(row["chain"],page_hash,ordinal,len(records))
                db.execute("INSERT INTO dataset_pages VALUES(?,?,?,?,?,?,?)",(self.owner,self.game,version,ordinal,page_hash,len(records),chain))
                db.execute("UPDATE dataset_versions SET rows=rows+?,next_page=next_page+1,chain=? WHERE owner=? AND game=? AND id=?",
                    (len(records),chain,self.owner,self.game,version))
                db.execute("COMMIT")
                return {"page_hash":page_hash,"rows":len(records),"chain":chain,"replayed":False}
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def seal(self,version):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=self._get(db,version,("building","sealed"))
                if row["rows"]!=row["expected_rows"] or row["chain"]!=row["expected_chain"]:
                    raise CatalogueHeld("dataset version not complete")
                db.execute("UPDATE dataset_versions SET state='sealed' WHERE owner=? AND game=? AND id=?",
                    (self.owner,self.game,version))
                db.execute("COMMIT")
                return {**self._public(row),"state":"sealed","source_verified":False,"training_allowed":False}
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def query(self,version,*,q=None,after=None,limit=32):
        if type(limit) is not int or not 1<=limit<=100:raise ValueError("dataset page")
        after=key(after) if after else ""
        with self._db() as db:
            row=self._get(db,version)
            args=[self.owner,self.game,version,after]
            match=""
            join=""
            if q is not None:
                terms=re.findall(r"[^\W_]+",clean(q,256))[:12]
                if not terms:raise ValueError("search terms required")
                fts='owner : "'+self.owner+'" AND game : "'+self.game+'" AND version : "'+version+'" AND search_text : ('+' AND '.join('"'+w+'"' for w in terms)+')'
                join=" JOIN dataset_fts ON dataset_fts.rowid=r.fts_row"
                match=" AND dataset_fts MATCH ?";args.append(fts)
            args.append(limit+1)
            deadline=time.monotonic()+2
            db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
            try:
                result=db.execute("""SELECT r.record_key,r.data_json,r.row_hash FROM dataset_records r"""+join+
                    " WHERE r.owner=? AND r.game=? AND r.version=? AND r.record_key>?"+match+
                    " ORDER BY r.record_key LIMIT ?",args).fetchall()
            finally:db.set_progress_handler(None,0)
            self._get(db,version)
        output=[]
        for item in result[:limit]:
            if hashlib.sha256(item["data_json"].encode()).hexdigest()!=item["row_hash"]:raise CatalogueHeld("record witness")
            output.append({"key":item["record_key"],"record":json.loads(item["data_json"]),"sha256":item["row_hash"]})
        return {"version":version,"label":row["label"],"records":output,
                "next_cursor":result[limit-1]["record_key"] if len(result)>limit else None,
                "source_verified":False,"training_allowed":False}

    def edges(self,version,record,*,reverse=False,limit=100):
        if type(reverse) is not bool or type(limit) is not int or not 1<=limit<=100:raise ValueError("edge bounds")
        record=key(record)
        with self._db() as db:
            self._get(db,version)
            field="target" if reverse else "record_key"
            rows=db.execute("SELECT record_key,relation,target FROM dataset_edges WHERE owner=? AND game=? AND version=? AND "+field+"=? ORDER BY relation,record_key,target LIMIT ?",
                (self.owner,self.game,version,record,limit+1)).fetchall()
            self._get(db,version)
        return {"edges":[dict(r) for r in rows[:limit]],"truncated":len(rows)>limit,"source_verified":False}

    def revoke(self,version):
        with self._db() as db:
            result=db.execute("UPDATE dataset_versions SET state='revoked',expires_at=0 WHERE owner=? AND game=? AND id=? AND state IN ('building','sealed')",
                (self.owner,self.game,_id(version)))
        return {"revoked":result.rowcount==1,"physical_erasure":False}

    def collect(self,version,*,limit=512):
        """Bounded exact deletion of record/edge/FTS rows after expiry or revoke."""
        if type(limit) is not int or not 1<=limit<=512:raise ValueError("collect bounds")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=self._get(db,version,("building","sealed","revoked","erased"),live=False)
                if row["state"]!="revoked" and row["state"]!="erased" and row["expires_at"]>time.time():
                    raise CatalogueHeld("live dataset cannot be erased")
                db.execute("UPDATE dataset_versions SET state='revoked' WHERE owner=? AND game=? AND id=? AND state!='erased'",
                    (self.owner,self.game,version))
                rows=db.execute("SELECT record_key,fts_row FROM dataset_records WHERE owner=? AND game=? AND version=? ORDER BY record_key LIMIT ?",
                    (self.owner,self.game,version,limit)).fetchall()
                for r in rows:
                    args=(self.owner,self.game,version,r["record_key"])
                    db.execute("DELETE FROM dataset_edges WHERE owner=? AND game=? AND version=? AND record_key=?",args)
                    db.execute("DELETE FROM dataset_fts WHERE rowid=?",(r["fts_row"],))
                    db.execute("DELETE FROM dataset_records WHERE owner=? AND game=? AND version=? AND record_key=?",args)
                if len(rows)<limit:
                    pages=db.execute("SELECT ordinal FROM dataset_pages WHERE owner=? AND game=? AND version=? ORDER BY ordinal LIMIT ?",
                        (self.owner,self.game,version,limit)).fetchall()
                    db.executemany("DELETE FROM dataset_pages WHERE owner=? AND game=? AND version=? AND ordinal=?",
                        [(self.owner,self.game,version,x["ordinal"]) for x in pages])
                    if len(pages)<limit:
                        db.execute("UPDATE dataset_versions SET state='erased' WHERE owner=? AND game=? AND id=?",(self.owner,self.game,version))
                final=self._get(db,version,("revoked","erased"),live=False)
                db.execute("COMMIT")
                return {"removed_records":len(rows),"complete":final["state"]=="erased","secure_erasure":False}
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise


    def versions(self,*,after=None,limit=32):
        if type(limit) is not int or not 1<=limit<=100:raise ValueError("dataset version page")
        with self._db() as db:
            rows=db.execute("""SELECT * FROM dataset_versions WHERE owner=? AND game=? AND id>?
                AND expires_at>? AND state IN ('building','sealed') ORDER BY id LIMIT ?""",
                (self.owner,self.game,_id(after) if after else "",int(time.time()),limit+1)).fetchall()
        return {"versions":[self._public(x) for x in rows[:limit]],
                "next_cursor":rows[limit-1]["id"] if len(rows)>limit else None,
                "source_verified":False,"training_allowed":False}

    @classmethod
    def operator_shard(cls,index):
        if type(index) is not int or not 0<=index<SHARDS:raise ValueError("shard number")
        root=_root()
        path=root/("game-data-"+format(index,"02x")+".sqlite3")
        if not path.exists():return None
        obj=cls.__new__(cls)
        obj.root=root;obj.path=path
        st=root.stat();obj.root_id=(st.st_dev,st.st_ino)
        st=path.stat();obj.file_id=(st.st_dev,st.st_ino)
        obj.scope=None;obj.owner=None;obj.game=None
        return obj


def sweep_dataset_shard(corpus_path):
    """Persistent round robin maintenance; no cross-owner result disclosure."""
    with GameCorpus(corpus_path)._db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS dataset_maintenance(singleton INTEGER PRIMARY KEY CHECK(singleton=1),cursor INTEGER NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("INSERT OR IGNORE INTO dataset_maintenance VALUES(1,0)")
            idx=db.execute("SELECT cursor FROM dataset_maintenance WHERE singleton=1").fetchone()[0]
            db.execute("UPDATE dataset_maintenance SET cursor=? WHERE singleton=1",((idx+1)%SHARDS,))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    obj=DatasetShard.operator_shard(idx)
    if obj is None:return {"scanned":0,"removed_records":0}
    with obj._db() as db:
        rows=db.execute("""SELECT owner,game,id FROM dataset_versions WHERE state!='erased'
            AND (expires_at<=? OR state='revoked') ORDER BY expires_at,owner,game,id LIMIT 2""",(int(time.time()),)).fetchall()
    total=0
    for row in rows:
        obj.owner=_id(row["owner"]);obj.game=_id(row["game"])
        total+=obj.collect(row["id"])["removed_records"]
    return {"scanned":len(rows),"removed_records":total,"secure_erasure":False}
