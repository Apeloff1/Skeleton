"""Journaled chunk/manifest layer over Dragon's private physical volumes.

Exclusive operator-managed storage component. Use dedicated volumes and ledger
for this layer; mixing direct BulkArchive writes or erases with the manifest
manager is unsupported. It does not grant source retention or model rights.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

from core.dragon_hoarder_bulk import BulkArchive,Receipt,StorageHeld,owner_key

BLOCK=2*1024*1024
MAX_BLOCKS=512
MAX_DOCUMENT=BLOCK*MAX_BLOCKS
MAX_MANIFESTS=1_000_000_000
HEX=re.compile(r"[a-f0-9]{64}\Z")
SCHEMA="""
CREATE TABLE IF NOT EXISTS manifest_counts(owner TEXT PRIMARY KEY,total INTEGER NOT NULL CHECK(total>=0)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS manifests(
 owner TEXT NOT NULL, id TEXT NOT NULL, logical_key TEXT NOT NULL,
 scope_json TEXT NOT NULL, expected_hash TEXT NOT NULL,
 expected_bytes INTEGER NOT NULL CHECK(expected_bytes BETWEEN 1 AND 1073741824),
 state TEXT NOT NULL CHECK(state IN ('building','sealed','aborted')),
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
 PRIMARY KEY(owner,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS chunks(
 owner TEXT NOT NULL, digest TEXT NOT NULL, volume TEXT NOT NULL,
 raw_bytes INTEGER NOT NULL CHECK(raw_bytes BETWEEN 1 AND 2097152),
 compressed_bytes INTEGER,
 PRIMARY KEY(owner,digest)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS placements(
 owner TEXT NOT NULL, manifest TEXT NOT NULL, ordinal INTEGER NOT NULL,
 digest TEXT NOT NULL, PRIMARY KEY(owner,manifest,ordinal),
 FOREIGN KEY(owner,manifest) REFERENCES manifests(owner,id),
 FOREIGN KEY(owner,digest) REFERENCES chunks(owner,digest)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS chunk_references ON placements(owner,digest);
CREATE TABLE IF NOT EXISTS manifest_garbage(
 owner TEXT NOT NULL, manifest TEXT NOT NULL, digest TEXT NOT NULL,
 PRIMARY KEY(owner,manifest,digest)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS manifest_lifecycle ON manifests(state,updated_at,owner,id);
CREATE INDEX IF NOT EXISTS manifest_history ON manifests(owner,logical_key,created_at DESC,id);
"""


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _hex(value):
    if not isinstance(value,str) or not HEX.fullmatch(value):
        raise ValueError("digest required")
    return value


def _key(value):
    if not isinstance(value,str) or not 1<=len(value)<=256 or value.strip()!=value or "\x00" in value:
        raise ValueError("invalid key")
    return value


class ManifestArchive:
    def __init__(self,path:Path,bulk:BulkArchive,*,create=True):
        self.path=Path(path)
        self.bulk=bulk
        if not self.path.is_absolute() or self.path.parent.resolve(strict=True)!=self.path.parent:
            raise ValueError("canonical private manifest directory required")
        parent=self.path.parent.stat()
        if os.name=="posix" and (parent.st_uid!=os.getuid() or parent.st_mode & 0o077):
            raise ValueError("manifest directory is not private")
        if self.path.is_symlink():
            raise StorageHeld("unsafe manifest path")
        if not self.path.exists():
            if not create:raise StorageHeld("manifest ledger missing")
            try:
                fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        self.file_identity=(self.path.stat().st_dev,self.path.stat().st_ino)
        with self._db() as db:
            meta=db.execute("CREATE TABLE IF NOT EXISTS manifest_configuration(singleton INTEGER PRIMARY KEY CHECK(singleton=1), volumes TEXT NOT NULL)")
            del meta
            volume_names=json.dumps(sorted(self.bulk.volumes))
            db.execute("INSERT OR IGNORE INTO manifest_configuration VALUES(1,?)",(volume_names,))
            configured=db.execute("SELECT volumes FROM manifest_configuration WHERE singleton=1").fetchone()[0]
            if configured!=volume_names:
                # Placement identities are persisted per chunk. Additive topology
                # may distribute NEW chunks without remapping any existing bytes.
                # Never permit a removal/rename or implicit relocation.
                try:
                    before=json.loads(configured)
                    after=json.loads(volume_names)
                    additive=(isinstance(before,list) and all(isinstance(x,str) for x in before)
                              and len(before)==len(set(before)) and set(before)<set(after))
                except (ValueError,TypeError):
                    additive=False
                if os.getenv("SKL_DRAGON_HOARDER_ALLOW_VOLUME_EXPANSION")!="1" or not additive:
                    raise StorageHeld("volume topology changed; explicit additive expansion or relocation required")
                db.execute("BEGIN IMMEDIATE")
                try:
                    latest=db.execute("SELECT volumes FROM manifest_configuration WHERE singleton=1").fetchone()[0]
                    if latest!=configured:
                        raise StorageHeld("volume topology changed during expansion")
                    # Every already-admitted placement must remain addressable.
                    known=set(after)
                    if any(row[0] not in known for row in db.execute("SELECT DISTINCT volume FROM chunks")):
                        raise StorageHeld("existing chunk placement unavailable")
                    db.execute("UPDATE manifest_configuration SET volumes=? WHERE singleton=1",(volume_names,))
                    db.execute("COMMIT")
                except BaseException:
                    if db.in_transaction:db.execute("ROLLBACK")
                    raise

    @contextmanager
    def _db(self):
        if self.path.is_symlink() or not self.path.is_file() or self.path.parent.resolve(strict=True)!=self.path.parent:
            raise StorageHeld("manifest path changed")
        st=self.path.stat()
        if (st.st_dev,st.st_ino)!=self.file_identity or os.name=="posix" and (st.st_uid!=os.getuid() or st.st_mode&0o077):
            raise StorageHeld("manifest identity or permission changed")
        for suffix in ("-wal","-shm","-journal"):
            path=Path(str(self.path)+suffix)
            # SQLite may remove an ephemeral sidecar during another close.
            # Inspect a single inode, then reobserve only an unlinked inode.
            # Live symlinks, hardlinks, nonregular and nonprivate files fail.
            for attempt in range(3):
                try:
                    info=path.lstat()
                except FileNotFoundError:
                    break
                if not stat.S_ISREG(info.st_mode) or os.name=="posix" and (
                        info.st_uid!=os.getuid() or info.st_mode&0o077):
                    raise StorageHeld("unsafe manifest sidecar")
                if info.st_nlink==1:
                    break
                if info.st_nlink!=0 or attempt==2:
                    raise StorageHeld("unsafe manifest sidecar")
        db=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        db.row_factory=sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(SCHEMA)
            yield db
        finally:
            db.close()

    @contextmanager
    def _write(self):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction: db.execute("ROLLBACK")
                raise

    def _volume(self,owner,digest):
        # Stable rendezvous assignment, independent of caller order. Existing
        # chunks retain their recorded volume; topology is frozen per ledger.
        return max(self.bulk.volumes,key=lambda name:_hash((owner+digest+":"+name).encode()))

    def begin(self,scope,*,logical_key,operation,expected_hash,expected_bytes):
        owner=owner_key(scope)
        logical_key=_key(logical_key)
        operation=_key(operation)
        expected_hash=_hex(expected_hash)
        if type(expected_bytes) is not int or not 1<=expected_bytes<=MAX_DOCUMENT:
            raise ValueError("document size")
        identifier=_hash(json.dumps([owner,logical_key,operation],separators=(",",":")).encode())
        now=int(time.time())
        with self._write() as db:
            row=db.execute("SELECT * FROM manifests WHERE owner=? AND id=?",(owner,identifier)).fetchone()
            if row:
                if (row["expected_hash"],row["expected_bytes"])!=(expected_hash,expected_bytes):
                    raise StorageHeld("manifest identity collision")
                return {"manifest":identifier,"state":row["state"],"replayed":True}
            count=db.execute("SELECT total FROM manifest_counts WHERE owner=?",(owner,)).fetchone()
            if count is None:
                total=db.execute("SELECT COUNT(*) FROM manifests WHERE owner=?",(owner,)).fetchone()[0]
                db.execute("INSERT INTO manifest_counts VALUES(?,?)",(owner,total))
            else:total=count["total"]
            if total>=MAX_MANIFESTS:
                raise StorageHeld("manifest cap")
            db.execute("INSERT INTO manifests VALUES(?,?,?,?,?,?,'building',?,?)",
                       (owner,identifier,logical_key,json.dumps(scope,sort_keys=True),expected_hash,expected_bytes,now,now))
            db.execute("UPDATE manifest_counts SET total=total+1 WHERE owner=?",(owner,))
        return {"manifest":identifier,"state":"building","replayed":False}

    def _manifest(self,db,owner,identifier,states):
        row=db.execute("SELECT * FROM manifests WHERE owner=? AND id=?",(owner,_hex(identifier))).fetchone()
        if not row or row["state"] not in states:
            raise StorageHeld("manifest not in required state")
        return row

    def _bound(self,row,ordinal):
        blocks=(row["expected_bytes"]+BLOCK-1)//BLOCK
        if type(ordinal) is not int or not 0<=ordinal<blocks<=MAX_BLOCKS:
            raise ValueError("chunk ordinal")
        return min(BLOCK,row["expected_bytes"]-ordinal*BLOCK)

    def append(self,scope,identifier,ordinal,data):
        """Journal intent before cross-database publication; retry exact bytes."""
        owner=owner_key(scope)
        if not isinstance(data,bytes) or not 1<=len(data)<=BLOCK:
            raise ValueError("chunk size")
        digest=_hash(data)
        with self._write() as db:
            row=self._manifest(db,owner,identifier,{"building"})
            if len(data)!=self._bound(row,ordinal):
                raise ValueError("chunk length differs from manifest")
            prior=db.execute("SELECT digest FROM placements WHERE owner=? AND manifest=? AND ordinal=?",
                             (owner,identifier,ordinal)).fetchone()
            if prior and prior["digest"]!=digest:
                raise StorageHeld("chunk ordinal already binds different bytes")
            db.execute("INSERT OR IGNORE INTO chunks(owner,digest,volume,raw_bytes) VALUES(?,?,?,?)",
                       (owner,digest,self._volume(owner,digest),len(data)))
            db.execute("INSERT OR IGNORE INTO placements VALUES(?,?,?,?)",(owner,identifier,ordinal,digest))
            db.execute("UPDATE manifests SET updated_at=? WHERE owner=? AND id=?",(int(time.time()),owner,identifier))
        # Keep the ledger write lock during publication; abort/GC cannot race
        # this write. If killed after payload commit, journal intent survives.
        with self._write() as db:
            self._manifest(db,owner,identifier,{"building"})
            chunk=db.execute("""SELECT c.* FROM chunks c JOIN placements p
                ON c.owner=p.owner AND c.digest=p.digest
                WHERE p.owner=? AND p.manifest=? AND p.ordinal=?""",(owner,identifier,ordinal)).fetchone()
            if not chunk or chunk["digest"]!=digest or chunk["raw_bytes"]!=len(data):
                raise StorageHeld("journal intent changed")
            receipt=self.bulk.put(chunk["volume"],scope,data)
            if (receipt.digest,receipt.raw_bytes)!=(digest,len(data)):
                raise StorageHeld("bulk acknowledgement differs")
            if chunk["compressed_bytes"] is not None and chunk["compressed_bytes"]!=receipt.compressed_bytes:
                raise StorageHeld("bulk storage representation changed")
            db.execute("UPDATE chunks SET compressed_bytes=? WHERE owner=? AND digest=?",
                       (receipt.compressed_bytes,owner,digest))
        return {"manifest":identifier,"ordinal":ordinal,"digest":digest,"stored":True}

    def _placements(self,db,owner,identifier):
        return db.execute("""SELECT p.ordinal,c.digest,c.volume,c.raw_bytes,c.compressed_bytes
                    FROM placements p JOIN chunks c ON c.owner=p.owner AND c.digest=p.digest
                    WHERE p.owner=? AND p.manifest=? ORDER BY p.ordinal""",(owner,identifier)).fetchall()

    def _receipt(self,owner,row):
        if row["compressed_bytes"] is None:
            raise StorageHeld("unpublished chunk")
        return Receipt(row["volume"],owner,row["digest"],row["raw_bytes"],row["compressed_bytes"])

    def seal(self,scope,identifier):
        owner=owner_key(scope)
        # Explicit operation; verifies full original hash before publication.
        # Holds the manifest ledger lock, never a network worker. For large
        # deployments run sealing on a dedicated storage worker.
        with self._write() as db:
            row=self._manifest(db,owner,identifier,{"building","sealed"})
            chunks=self._placements(db,owner,identifier)
            expected=(row["expected_bytes"]+BLOCK-1)//BLOCK
            if len(chunks)!=expected:
                raise StorageHeld("manifest incomplete")
            h=hashlib.sha256()
            size=0
            for ordinal,chunk in enumerate(chunks):
                if chunk["ordinal"]!=ordinal or chunk["raw_bytes"]!=self._bound(row,ordinal):
                    raise StorageHeld("chunk ordering or length mismatch")
                if chunk["compressed_bytes"] is None:
                    recovered=self.bulk.lookup(chunk["volume"],scope,chunk["digest"])
                    if recovered is None or recovered.raw_bytes!=chunk["raw_bytes"]:
                        raise StorageHeld("publication uncertain; retry chunk")
                    db.execute("UPDATE chunks SET compressed_bytes=? WHERE owner=? AND digest=?",
                               (recovered.compressed_bytes,owner,chunk["digest"]))
                    receipt=recovered
                else:
                    receipt=self._receipt(owner,chunk)
                data=self.bulk.read(scope,receipt)
                h.update(data)
                size+=len(data)
            if size!=row["expected_bytes"] or h.hexdigest()!=row["expected_hash"]:
                raise StorageHeld("whole document witness differs")
            db.execute("UPDATE manifests SET state='sealed',updated_at=? WHERE owner=? AND id=?",
                       (int(time.time()),owner,identifier))
            return {"manifest":identifier,"sha256":h.hexdigest(),"bytes":size,"chunks":expected,
                    "sealed":True,"source_authorized":False}

    def read_chunk(self,scope,identifier,ordinal):
        """Read an exact chunk from a sealed manifest; not source-use authority."""
        owner=owner_key(scope)
        with self._write() as db:
            row=self._manifest(db,owner,identifier,{"sealed"})
            size=self._bound(row,ordinal)
            chunk=db.execute("""SELECT c.* FROM placements p JOIN chunks c
                ON c.owner=p.owner AND c.digest=p.digest
                WHERE p.owner=? AND p.manifest=? AND p.ordinal=?""",(owner,identifier,ordinal)).fetchone()
            if not chunk or chunk["raw_bytes"]!=size:
                raise StorageHeld("sealed chunk unavailable")
            return self.bulk.read(scope,self._receipt(owner,chunk))

    def abort(self,scope,identifier):
        """Explicit caller-authorized logical removal of this manifest reference."""
        owner=owner_key(scope)
        with self._write() as db:
            row=self._manifest(db,owner,identifier,{"building","sealed","aborted"})
            if row["state"]=="aborted":
                return False
            db.execute("""INSERT OR IGNORE INTO manifest_garbage
                SELECT owner,manifest,digest FROM placements WHERE owner=? AND manifest=?""",(owner,identifier))
            db.execute("DELETE FROM placements WHERE owner=? AND manifest=?",(owner,identifier))
            db.execute("UPDATE manifests SET state='aborted',updated_at=? WHERE owner=? AND id=?",
                       (int(time.time()),owner,identifier))
            return True

    def collect(self,scope,*,limit=32):
        """Garbage collect only journaled, zero-reference objects for this owner.

        Lock order is manifest ledger then payload DB. A crash after erasure
        leaves a harmless journal row; next pulse confirms absence and cleans.
        """
        owner=owner_key(scope)
        if type(limit) is not int or not 1<=limit<=128:
            raise ValueError("collection bound")
        count=0
        for _ in range(limit):
            with self._write() as db:
                chunk=db.execute("""SELECT c.* FROM chunks c WHERE c.owner=? AND NOT EXISTS
                    (SELECT 1 FROM placements p WHERE p.owner=c.owner AND p.digest=c.digest)
                    ORDER BY c.digest LIMIT 1""",(owner,)).fetchone()
                if not chunk:
                    break
                receipt=self.bulk.lookup(chunk["volume"],scope,chunk["digest"])
                if receipt:
                    if receipt.raw_bytes!=chunk["raw_bytes"]:
                        raise StorageHeld("garbage candidate witness differs")
                    self.bulk.erase_unreferenced(scope,receipt)
                db.execute("DELETE FROM chunks WHERE owner=? AND digest=?",(owner,chunk["digest"]))
                count+=1
        return {"collected":count,"physical_secure_erasure":False}

    def history(self,scope,logical_key,*,limit=32,before=None):
        owner=owner_key(scope)
        logical_key=_key(logical_key)
        if type(limit) is not int or not 1<=limit<=128:
            raise ValueError("history bound")
        args=[owner,logical_key]
        where=""
        if before is not None:
            if not isinstance(before,(list,tuple)) or len(before)!=2 or type(before[0]) is not int:
                raise ValueError("history cursor")
            where=" AND (created_at,id)<(?,?)"
            args += [before[0],_hex(before[1])]
        args.append(limit+1)
        with self._db() as db:
            rows=db.execute("""SELECT id,expected_hash,expected_bytes,state,created_at,updated_at FROM manifests
                WHERE owner=? AND logical_key=?"""+where+" ORDER BY created_at DESC,id DESC LIMIT ?",args).fetchall()
        return {"manifests":[dict(row) for row in rows[:limit]],
                "next_cursor":[rows[limit-1]["created_at"],rows[limit-1]["id"]] if len(rows)>limit else None}

    def usage(self,scope):
        owner=owner_key(scope)
        with self._db() as db:
            states={r["state"]:r["n"] for r in db.execute("SELECT state,COUNT(*) AS n FROM manifests WHERE owner=? GROUP BY state",(owner,))}
            row=db.execute("SELECT COUNT(*) AS n,COALESCE(SUM(raw_bytes),0) AS raw,COALESCE(SUM(compressed_bytes),0) AS compressed FROM chunks WHERE owner=?",(owner,)).fetchone()
            return {"manifests":states,"unique_chunks":row["n"],"unique_raw_bytes":row["raw"],
                    "unique_compressed_bytes":row["compressed"],"capacity_guaranteed":False}


    def abort_intent(self,scope,*,logical_key,operation,expected_hash,expected_bytes):
        """Create a permanent tombstone even if an external write has not begun."""
        receipt=self.begin(scope,logical_key=logical_key,operation=operation,
                           expected_hash=expected_hash,expected_bytes=expected_bytes)
        identifier=receipt["manifest"]
        self.abort(scope,identifier)
        return identifier

    def collect_manifest(self,scope,identifier,*,limit=32):
        """Resolve exactly this tombstone's pending garbage, including crash replay."""
        owner=owner_key(scope)
        identifier=_hex(identifier)
        if type(limit) is not int or not 1<=limit<=128:
            raise ValueError("collection bound")
        processed=erased=0
        for _ in range(limit):
            with self._write() as db:
                self._manifest(db,owner,identifier,{"aborted"})
                row=db.execute("""SELECT digest FROM manifest_garbage
                    WHERE owner=? AND manifest=? ORDER BY digest LIMIT 1""",(owner,identifier)).fetchone()
                if row is None:
                    break
                digest=row["digest"]
                live=db.execute("SELECT 1 FROM placements WHERE owner=? AND digest=? LIMIT 1",(owner,digest)).fetchone()
                if not live:
                    chunk=db.execute("SELECT * FROM chunks WHERE owner=? AND digest=?",(owner,digest)).fetchone()
                    if chunk:
                        receipt=self.bulk.lookup(chunk["volume"],scope,digest)
                        if receipt:
                            if receipt.raw_bytes!=chunk["raw_bytes"]:
                                raise StorageHeld("manifest garbage witness differs")
                            self.bulk.erase_unreferenced(scope,receipt)
                            erased+=1
                        db.execute("DELETE FROM chunks WHERE owner=? AND digest=?",(owner,digest))
                db.execute("DELETE FROM manifest_garbage WHERE owner=? AND manifest=? AND digest=?",
                           (owner,identifier,digest))
                processed+=1
        with self._db() as db:
            remaining=db.execute("SELECT COUNT(*) FROM manifest_garbage WHERE owner=? AND manifest=?",
                                 (owner,identifier)).fetchone()[0]
        return {"processed":processed,"erased":erased,"remaining":remaining,"physical_secure_erasure":False}
