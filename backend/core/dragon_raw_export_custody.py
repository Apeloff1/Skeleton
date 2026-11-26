"""Private, bounded retention of independently supplied raw export bytes.

No crawler response is reconstructed or re-fetched. Raw bytes are not indexed
or sent to a model. A finite owner-scoped retention grant is independent of
capture, import and publisher-signature evidence. Expired objects are hidden
from reads and purge is explicit/bounded; SQLite deletion is not secure
physical erasure or backup revocation.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import time

from core.dragon_dataset_ingest import fingerprint, source_stream
from core.dragon_owner_shards import _private,_open
from core.dragon_hoarder_bulk import owner_key

BLOCK=1024*1024
MAX_OBJECT=512*BLOCK
MAX_OWNER_BYTES=4*1024*BLOCK
MAX_TOTAL_BYTES=32*1024*BLOCK
MAX_OBJECTS=16384
RESERVE=512*BLOCK
HEX=re.compile(r"[a-f0-9]{64}\Z")
SCHEMA="""
CREATE TABLE IF NOT EXISTS raw_exports(
 owner TEXT NOT NULL,id TEXT NOT NULL,sha256 TEXT NOT NULL,bytes INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,created INTEGER NOT NULL,state TEXT NOT NULL
 CHECK(state IN ('sealed','erased')),PRIMARY KEY(owner,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS raw_export_chunks(
 owner TEXT NOT NULL,id TEXT NOT NULL,ordinal INTEGER NOT NULL,
 block_sha TEXT NOT NULL,body BLOB NOT NULL,PRIMARY KEY(owner,id,ordinal),
 FOREIGN KEY(owner,id) REFERENCES raw_exports(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS raw_export_expiry ON raw_exports(state,expires_at,owner,id);
"""


def _hex(value):
    if not isinstance(value,str) or not HEX.fullmatch(value):raise ValueError("exact SHA-256 required")
    return value


def _owner(scope):
    if not isinstance(scope,dict) or set(scope)!={"tenant_id","owner_id"}:
        raise ValueError("explicit owner scope required")
    if any(not isinstance(x,str) or not 1<=len(x)<=256 or x.strip()!=x for x in scope.values()):
        raise ValueError("invalid owner scope")
    return owner_key(scope)


class RawExportCustody:
    def __init__(self,path,*,create=False):
        self.path=Path(path)
        if create and not self.path.exists():
            _private(self.path,create=True)
            with _open(self.path) as db:db.executescript(SCHEMA)
        _private(self.path)
        with _open(self.path) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='raw_exports'").fetchone():
                raise ValueError("explicit raw export store initialization required")

    def retain(self,scope,path,*,expected_sha,operation,retention_seconds,rights_acknowledged):
        path=Path(path);witness=fingerprint(path)
        return self._retain(scope,size=witness[2],stream_factory=lambda:source_stream(path,None,witness),
            expected_sha=expected_sha,operation=operation,retention_seconds=retention_seconds,
            rights_acknowledged=rights_acknowledged)

    def retain_response(self,scope,body,*,expected_sha,operation,retention_seconds,rights_acknowledged):
        """Retain bounded in-memory decoded HTTP entity bytes, not headers or wire framing.

        The authorized connector must independently evaluate response rights
        before invoking this internal method. No request or URL is accepted.
        """
        if type(body) is not bytes or not 1<=len(body)<=4_000_000:
            raise ValueError("bounded immutable HTTP entity required")
        return self._retain(scope,size=len(body),stream_factory=lambda:BytesIO(body),
            expected_sha=expected_sha,operation=operation,retention_seconds=retention_seconds,
            rights_acknowledged=rights_acknowledged)

    def _retain(self,scope,*,size,stream_factory,expected_sha,operation,retention_seconds,rights_acknowledged):
        owner=_owner(scope);expected_sha=_hex(expected_sha)
        if (rights_acknowledged is not True or type(retention_seconds) is not int
                or not 300<=retention_seconds<=30*86400
                or not isinstance(operation,str) or not 1<=len(operation)<=128 or operation.strip()!=operation):
            raise ValueError("explicit finite raw export retention grant required")
        if not 1<=size<=MAX_OBJECT:raise ValueError("raw export object byte cap")
        identifier=hashlib.sha256((owner+"\0"+operation).encode()).hexdigest()
        now=int(time.time())
        # Verify full bytes before opening a write transaction; verify again
        # during streaming insertion. The private store is the trust boundary.
        with stream_factory() as stream:
            h=hashlib.sha256()
            for chunk in iter(lambda:stream.read(BLOCK),b""):h.update(chunk)
        if h.hexdigest()!=expected_sha:raise ValueError("raw export SHA-256 differs")
        with _open(self.path) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA secure_delete=ON")
            db.execute("BEGIN IMMEDIATE")
            old=db.execute("SELECT * FROM raw_exports WHERE owner=? AND id=?",(owner,identifier)).fetchone()
            if old is not None:
                if old["state"]!="sealed" or old["expires_at"]<=now or old["sha256"]!=expected_sha or old["bytes"]!=size:
                    raise ValueError("raw export operation not replayable")
                db.execute("COMMIT")
                return self._receipt(old,replayed=True)
            total,count=db.execute("SELECT COALESCE(SUM(CASE WHEN state='sealed' THEN bytes ELSE 0 END),0),COUNT(*) FROM raw_exports").fetchone()
            used=db.execute("SELECT COALESCE(SUM(bytes),0) FROM raw_exports WHERE owner=? AND state='sealed'",(owner,)).fetchone()[0]
            if count>=MAX_OBJECTS or total+size>MAX_TOTAL_BYTES or used+size>MAX_OWNER_BYTES:
                raise ValueError("raw export storage quota")
            if shutil.disk_usage(self.path.parent).free<2*size+RESERVE:
                raise ValueError("raw export disk reserve")
            db.execute("INSERT INTO raw_exports VALUES(?,?,?,?,?,?,'sealed')",(owner,identifier,expected_sha,size,now+retention_seconds,now))
            h=hashlib.sha256();written=0;ordinal=0
            with stream_factory() as stream:
                for chunk in iter(lambda:stream.read(BLOCK),b""):
                    written+=len(chunk);h.update(chunk)
                    db.execute("INSERT INTO raw_export_chunks VALUES(?,?,?,?,?)",
                        (owner,identifier,ordinal,hashlib.sha256(chunk).hexdigest(),chunk))
                    ordinal+=1
            if written!=size or h.hexdigest()!=expected_sha or int(time.time())>=now+retention_seconds:
                raise ValueError("raw export changed or retention expired before commit")
            row=db.execute("SELECT * FROM raw_exports WHERE owner=? AND id=?",(owner,identifier)).fetchone()
            db.execute("COMMIT")
            return self._receipt(row,replayed=False)

    @staticmethod
    def _receipt(row,*,replayed):
        return {k:row[k] for k in ("id","sha256","bytes","expires_at","state")} | {
            "replayed":replayed,"raw_bytes_retained":True,"network_executed":False,
            "training_allowed":False,"source_rights_verified":False}

    def metadata(self,scope,identifier):
        owner=_owner(scope);_hex(identifier)
        with _open(self.path) as db:
            row=db.execute("SELECT * FROM raw_exports WHERE owner=? AND id=? AND state='sealed' AND expires_at>?",
                (owner,identifier,int(time.time()))).fetchone()
            if row is None:raise LookupError("raw export unavailable")
            return self._receipt(row,replayed=True)

    def read_chunk(self,scope,identifier,ordinal):
        owner=_owner(scope);_hex(identifier)
        if type(ordinal) is not int or not 0<=ordinal<MAX_OBJECT//BLOCK:raise ValueError("chunk ordinal")
        with _open(self.path) as db:
            row=db.execute("""SELECT c.body,c.block_sha,e.bytes,e.expires_at FROM raw_export_chunks c
                JOIN raw_exports e ON e.owner=c.owner AND e.id=c.id
                WHERE c.owner=? AND c.id=? AND c.ordinal=? AND e.state='sealed' AND e.expires_at>?""",
                (owner,identifier,ordinal,int(time.time()))).fetchone()
            if row is None:raise LookupError("raw export chunk unavailable")
            data=bytes(row["body"])
            if (len(data)!=min(BLOCK,row["bytes"]-ordinal*BLOCK)
                    or hashlib.sha256(data).hexdigest()!=row["block_sha"] or int(time.time())>=row["expires_at"]):
                raise ValueError("raw export chunk witness differs or expired")
            return data

    def purge_expired(self,scope,*,limit=4):
        owner=_owner(scope)
        if type(limit) is not int or not 1<=limit<=16:raise ValueError("purge bound")
        with _open(self.path) as db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("BEGIN IMMEDIATE")
            rows=db.execute("SELECT id FROM raw_exports WHERE owner=? AND state='sealed' AND expires_at<=? ORDER BY expires_at,id LIMIT ?",
                (owner,int(time.time()),limit)).fetchall()
            for row in rows:
                db.execute("DELETE FROM raw_export_chunks WHERE owner=? AND id=?",(owner,row["id"]))
                db.execute("UPDATE raw_exports SET state='erased' WHERE owner=? AND id=?",(owner,row["id"]))
            db.execute("COMMIT")
        return {"purged":len(rows),"physical_erasure_verified":False,"backup_erasure_verified":False}


def main(argv=None):
    import argparse,json
    from core.dragon_mongo_receipt import _read_json
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--store",type=Path,required=True);p.add_argument("--scope-json",type=Path,required=True)
    p.add_argument("--initialize",action="store_true")
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("retain")
    a.add_argument("--export",type=Path,required=True);a.add_argument("--sha256",required=True)
    a.add_argument("--operation",required=True);a.add_argument("--retention-seconds",type=int,required=True)
    a.add_argument("--acknowledge-retention-rights",action="store_true")
    m=sub.add_parser("metadata");m.add_argument("--id",required=True)
    q=sub.add_parser("purge-expired");q.add_argument("--limit",type=int,default=4)
    args=p.parse_args(argv)
    scope=_read_json(args.scope_json.expanduser().absolute());_owner(scope)
    store=RawExportCustody(args.store.expanduser().absolute(),create=args.initialize)
    if args.command=="retain":
        result=store.retain(scope,args.export.expanduser().absolute(),expected_sha=args.sha256,
             operation=args.operation,retention_seconds=args.retention_seconds,rights_acknowledged=args.acknowledge_retention_rights)
    elif args.command=="metadata":result=store.metadata(scope,args.id)
    else:result=store.purge_expired(scope,limit=args.limit)
    print(json.dumps(result,sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
