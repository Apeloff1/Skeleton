"""Restart-safe fixed-to-CDC migration inside the existing Hoarder ledger.

The canonical manifest identity, expected bytes and original SHA-256 do
not change. New chunks are journaled and sealed before a single SQLite
transaction switches references. Old chunks are reclaimed only through
the ordinary zero-reference collection path. No source rights originate
here; the application must supply the current authorized exact bytes.
"""
from __future__ import annotations

import hashlib
import json
import time

from core.dragon_content_chunks import lengths,split,encode_layout,MAX_BYTES
from core.dragon_hoarder_bulk import StorageHeld,owner_key
from core.dragon_hoarder_manifests import MAX_MANIFESTS,BLOCK,_hex

SCHEMA="""
CREATE TABLE IF NOT EXISTS manifest_migrations(
 owner TEXT NOT NULL, original TEXT NOT NULL, staging TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('building','switched','aborted')),
 started INTEGER NOT NULL, updated INTEGER NOT NULL,
 PRIMARY KEY(owner,original), UNIQUE(owner,staging),
 FOREIGN KEY(owner,original) REFERENCES manifests(owner,id),
 FOREIGN KEY(owner,staging) REFERENCES manifests(owner,id)
) WITHOUT ROWID;
"""


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _stage_id(owner,original):
    return _sha(json.dumps([owner,"dragon-migration:"+original,"content-defined-v1"],
        separators=(",",":")).encode())


def _read_locked(archive,db,scope,row):
    # Read all placements under the same ledger fence; individual chunk reads
    # across a concurrent layout switch are not a coherent snapshot.
    layout=archive._layout(db,row)
    chunks=archive._placements(db,row["owner"],row["id"])
    count=len(layout) if layout is not None else (row["expected_bytes"]+BLOCK-1)//BLOCK
    if len(chunks)!=count or row["expected_bytes"]>MAX_BYTES:
        raise StorageHeld("migration source layout unavailable")
    raw=bytearray()
    for i,chunk in enumerate(chunks):
        if chunk["ordinal"]!=i or chunk["raw_bytes"]!=archive._bound(row,i,layout):
            raise StorageHeld("migration placement differs")
        raw.extend(archive.bulk.read(scope,archive._receipt(row["owner"],chunk)))
    if len(raw)!=row["expected_bytes"] or _sha(raw)!=row["expected_hash"]:
        raise StorageHeld("migration source checksum differs")
    return bytes(raw)


def _prepare(archive,scope,identifier,raw,layout):
    owner=owner_key(scope);stage=_stage_id(owner,identifier)
    with archive._write() as db:
        row=archive._manifest(db,owner,identifier,{"sealed"})
        if row["expected_bytes"]!=len(raw) or row["expected_hash"]!=_sha(raw):
            raise StorageHeld("authorized original witness differs")
        if _read_locked(archive,db,scope,row)!=raw:
            raise StorageHeld("original exact byte comparison failed")
        journal=db.execute("SELECT * FROM manifest_migrations WHERE owner=? AND original=?",
                           (owner,identifier)).fetchone()
        active=archive._layout(db,row)
        if active is not None:
            if active!=layout:
                raise StorageHeld("existing content-defined layout differs")
            if journal is not None and journal["state"]!="switched":
                raise StorageHeld("migration journal inconsistent")
            return "already",stage if journal is not None else None
        if journal is not None:
            if journal["staging"]!=stage or journal["state"]!="building":
                raise StorageHeld("migration journal held")
            staged=archive._manifest(db,owner,stage,{"building","sealed"})
            if (staged["expected_hash"]!=row["expected_hash"] or staged["expected_bytes"]!=len(raw)
                    or archive._layout(db,staged)!=layout):
                raise StorageHeld("migration replay differs")
            return staged["state"],stage
        if db.execute("SELECT 1 FROM manifests WHERE owner=? AND id=?",(owner,stage)).fetchone():
            raise StorageHeld("migration stage identity already exists")
        existing=db.execute("SELECT total FROM manifest_counts WHERE owner=?",(owner,)).fetchone()
        total=existing[0] if existing else db.execute(
            "SELECT COUNT(*) FROM manifests WHERE owner=?",(owner,)).fetchone()[0]
        if total>=MAX_MANIFESTS:raise StorageHeld("manifest cap")
        now=int(time.time())
        db.execute("INSERT INTO manifests VALUES(?,?,?,?,?,?,'building',?,?)",
            (owner,stage,"dragon-migration:"+identifier,row["scope_json"],
             row["expected_hash"],len(raw),now,now))
        db.execute("INSERT INTO manifest_layouts VALUES(?,?,?,?)",(owner,stage,*encode_layout(layout,len(raw))))
        db.execute("INSERT INTO manifest_counts VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET total=excluded.total",
                   (owner,total+1))
        db.execute("INSERT INTO manifest_migrations VALUES(?,?,?,'building',?,?)",(owner,identifier,stage,now,now))
        return "building",stage


def _switch(archive,scope,identifier,stage,raw,layout):
    owner=owner_key(scope)
    with archive._write() as db:
        row=archive._manifest(db,owner,identifier,{"sealed"})
        journal=db.execute("SELECT * FROM manifest_migrations WHERE owner=? AND original=?",
                           (owner,identifier)).fetchone()
        if journal is None or journal["staging"]!=stage:
            raise StorageHeld("migration journal missing")
        if journal["state"]=="switched":
            if archive._layout(db,row)!=layout or _read_locked(archive,db,scope,row)!=raw:
                raise StorageHeld("switched migration witness differs")
            return False
        if journal["state"]!="building" or archive._layout(db,row) is not None:
            raise StorageHeld("migration no longer runnable")
        staged=archive._manifest(db,owner,stage,{"sealed"})
        if (archive._layout(db,staged)!=layout or _read_locked(archive,db,scope,staged)!=raw
                or _read_locked(archive,db,scope,row)!=raw):
            raise StorageHeld("migration readback differs")
        # Garbage is attached to the retired staging tombstone, not the
        # still-live original. Shared refs are checked by ordinary GC.
        db.execute("INSERT OR IGNORE INTO manifest_garbage SELECT owner,?,digest FROM placements "
                   "WHERE owner=? AND manifest=?",(stage,owner,identifier))
        db.execute("DELETE FROM placements WHERE owner=? AND manifest=?",(owner,identifier))
        db.execute("INSERT INTO placements SELECT owner,?,ordinal,digest FROM placements "
                   "WHERE owner=? AND manifest=?",(identifier,owner,stage))
        db.execute("INSERT INTO manifest_layouts VALUES(?,?,?,?)",
                   (owner,identifier,*encode_layout(layout,len(raw))))
        db.execute("DELETE FROM placements WHERE owner=? AND manifest=?",(owner,stage))
        now=int(time.time())
        db.execute("UPDATE manifests SET state='aborted',updated_at=? WHERE owner=? AND id=?",
                   (now,owner,stage))
        db.execute("UPDATE manifests SET updated_at=? WHERE owner=? AND id=?",(now,owner,identifier))
        db.execute("UPDATE manifest_migrations SET state='switched',updated=? WHERE owner=? AND original=?",
                   (now,owner,identifier))
        return True


def migrate(archive,scope,identifier,raw,*,collect_limit=128):
    _hex(identifier)
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_BYTES:
        raise ValueError("migration byte bound")
    if type(collect_limit) is not int or not 1<=collect_limit<=128:
        raise ValueError("migration cleanup bound")
    layout=lengths(raw)
    phase,stage=_prepare(archive,scope,identifier,raw,layout)
    switched=False
    if phase!="already":
        if phase=="building":
            for i,part in enumerate(split(raw,layout)):
                archive.append(scope,stage,i,part)
            archive.seal(scope,stage)
        switched=_switch(archive,scope,identifier,stage,raw,layout)
    # Reopen a new transaction after the commit and verify original identity.
    owner=owner_key(scope)
    with archive._write() as db:
        row=archive._manifest(db,owner,identifier,{"sealed"})
        if archive._layout(db,row)!=layout or _read_locked(archive,db,scope,row)!=raw:
            raise StorageHeld("committed migration readback differs")
    garbage=archive.collect_manifest(scope,stage,limit=collect_limit) if stage else {"remaining":0,"erased":0}
    return {"manifest":identifier,"sha256":_sha(raw),"bytes":len(raw),"chunks":len(layout),
            "layout":"content_defined_v1","switched":switched,"replayed":not switched,
            "readback_verified":True,"garbage_remaining":garbage["remaining"],
            "unreferenced_chunks_collected":garbage["erased"],
            "canonical_primary_replaced":False,"physical_secure_erasure":False}


def abort_related(db,owner,identifier):
    """Original deletion fences pending stage and transfers GC obligations."""
    row=db.execute("SELECT staging,state FROM manifest_migrations WHERE owner=? AND original=?",
                   (owner,identifier)).fetchone()
    if row is None:return
    stage=row["staging"]
    db.execute("INSERT OR IGNORE INTO manifest_garbage SELECT owner,?,digest FROM placements "
               "WHERE owner=? AND manifest=?",(identifier,owner,stage))
    db.execute("INSERT OR IGNORE INTO manifest_garbage SELECT owner,?,digest FROM manifest_garbage "
               "WHERE owner=? AND manifest=?",(identifier,owner,stage))
    db.execute("DELETE FROM placements WHERE owner=? AND manifest=?",(owner,stage))
    db.execute("DELETE FROM manifest_garbage WHERE owner=? AND manifest=?",(owner,stage))
    now=int(time.time())
    db.execute("UPDATE manifests SET state='aborted',updated_at=? WHERE owner=? AND id=?",(now,owner,stage))
    db.execute("UPDATE manifest_migrations SET state='aborted',updated=? WHERE owner=? AND original=?",
               (now,owner,identifier))
