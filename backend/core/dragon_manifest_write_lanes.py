"""Ten real manifest write ledgers per opted-in owner.

Keep legacy IDs, tombstones and payload keys. New IDs choose a stable range;
new nonzero lanes use disjoint physical chunk namespaces. Deduplication is
local to that namespace, so a different ledger can never erase its payload.
Provisioning is offline only. No filesystem or throughput claim.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import secrets

from core.dragon_hoarder_bulk import Receipt,StorageHeld,owner_key,_storage_owner
from core.dragon_hoarder_manifests import ManifestArchive,_hex,_key,_hash
from core.dragon_owner_shards import _private,_open,_table,ShardHeld

LANES=10
ENROLL="""CREATE TABLE IF NOT EXISTS manifest_write_enrollment(
 owner TEXT PRIMARY KEY,epoch TEXT NOT NULL CHECK(length(epoch)=64),
 next_collect INTEGER NOT NULL CHECK(next_collect BETWEEN 0 AND 9)
) WITHOUT ROWID"""
IDENTITY="""CREATE TABLE IF NOT EXISTS manifest_write_identity(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 owner TEXT NOT NULL,epoch TEXT NOT NULL,lane INTEGER NOT NULL CHECK(lane BETWEEN 1 AND 9)
)"""
HEX=re.compile(r"[a-f0-9]{64}\Z")


def _epoch(value):
    if not isinstance(value,str) or not HEX.fullmatch(value):
        raise StorageHeld("manifest partition epoch")
    return value


def _namespace(epoch,lane):
    return hashlib.sha256(("dragon-manifest-lane-v1:"+_epoch(epoch)+":"+str(lane)).encode()).hexdigest()


def _file(base,owner,epoch,lane):
    _epoch(owner);_epoch(epoch)
    if type(lane) is not int or not 1<=lane<LANES:raise ValueError("manifest lane")
    # Nested directory avoids exceeding filename length with user-chosen root
    # basename. This directory is private and adjacent to its owner ledger.
    return base.parent/(".dragon-manifest-"+epoch)/("lane-"+str(lane)+".sqlite3")


class PartitionBulk:
    """Manifest receipt facade; never accepts a caller-chosen physical owner."""
    def __init__(self,bulk,owner,namespace):
        self.bulk=bulk
        self.volumes=bulk.volumes
        self.owner=owner
        self.namespace=namespace

    def _scope(self,scope):
        if owner_key(scope)!=self.owner:raise StorageHeld("partition owner differs")

    def _receipt(self,scope,receipt):
        self._scope(scope)
        if not isinstance(receipt,Receipt) or receipt.scope_key!=self.owner:
            raise StorageHeld("logical partition receipt differs")
        return replace(receipt,scope_key=_storage_owner(scope,self.namespace))

    def put(self,volume,scope,raw):
        self._scope(scope)
        return replace(self.bulk.put(volume,scope,raw,namespace=self.namespace),scope_key=self.owner)

    def put_many(self,volume,scope,parts):
        self._scope(scope)
        return [replace(receipt,scope_key=self.owner) for receipt in
                self.bulk.put_many(volume,scope,parts,namespace=self.namespace)]

    def read_many(self,scope,receipts):
        self._scope(scope)
        return self.bulk.read_many(scope,[self._receipt(scope,r) for r in receipts],namespace=self.namespace)

    def lookup(self,volume,scope,digest):
        self._scope(scope)
        receipt=self.bulk.lookup(volume,scope,digest,namespace=self.namespace)
        return replace(receipt,scope_key=self.owner) if receipt else None

    def read(self,scope,receipt):
        return self.bulk.read(scope,self._receipt(scope,receipt),namespace=self.namespace)

    def erase_unreferenced(self,scope,receipt):
        return self.bulk.erase_unreferenced(scope,self._receipt(scope,receipt),namespace=self.namespace)


def provision(base,scope,*,offline_acknowledged=False):
    """Publish nine precreated partition identities after stopping every writer.

    The legacy file is lane zero and stays authoritative for all old IDs.
    Interrupted provisioning leaves unused files but no active enrollment.
    """
    if offline_acknowledged is not True:raise StorageHeld("stop all manifest writers first")
    owner=owner_key(scope)
    path,_=_private(base)
    epoch=secrets.token_hex(32)
    with _open(path) as db:
        db.execute(ENROLL)
        db.execute("BEGIN IMMEDIATE")
        try:
            prior=db.execute("SELECT epoch FROM manifest_write_enrollment WHERE owner=?",(owner,)).fetchone()
            if prior:raise StorageHeld("manifest write partition already enrolled")
            if not _table(db,"manifests"):raise StorageHeld("initialize manifest ledger first")
            folder=_file(path,owner,epoch,1).parent
            folder.mkdir(mode=0o700)
            for lane in range(1,LANES):
                child,_=_private(_file(path,owner,epoch,lane),create=True)
                if child.stat().st_dev!=path.stat().st_dev:raise StorageHeld("partition ledger device differs")
                with _open(child) as part:
                    part.execute(IDENTITY)
                    part.execute("INSERT INTO manifest_write_identity VALUES(1,?,?,?)",(owner,epoch,lane))
            db.execute("INSERT INTO manifest_write_enrollment VALUES(?,?,0)",(owner,epoch))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"epoch":epoch,"lanes":LANES,"legacy_ids_moved":False,"cross_lane_dedup":False}


class OwnerWriteLanes:
    def __init__(self,legacy,scope):
        self.legacy=legacy
        self.scope=scope
        self.owner=owner_key(scope)
        with _open(legacy.path) as db:
            self.epoch=None
            if _table(db,"manifest_write_enrollment"):
                row=db.execute("SELECT epoch FROM manifest_write_enrollment WHERE owner=?",(self.owner,)).fetchone()
                if row:self.epoch=_epoch(row[0])

    @property
    def enabled(self):
        return self.epoch is not None

    def identifier(self,logical_key,operation):
        return _hash(json.dumps([self.owner,_key(logical_key),_key(operation)],separators=(",",":")).encode())

    def _lane(self,identifier):
        identifier=_hex(identifier)
        if not self.enabled:return 0
        # Historic manifest IDs (including tombstones) always win. There
        # is no route replay fallback if a nonzero lane has disappeared.
        with _open(self.legacy.path) as db:
            if db.execute("SELECT 1 FROM manifests WHERE owner=? AND id=?",(self.owner,identifier)).fetchone():
                return 0
        return int(identifier[:16],16)%LANES

    def archive(self,lane):
        if lane==0:return self.legacy
        if not self.enabled:raise StorageHeld("manifest partition unenrolled")
        path=_file(self.legacy.path,self.owner,self.epoch,lane)
        try:
            path,identity=_private(path)
            if path.stat().st_dev!=self.legacy.path.stat().st_dev:raise StorageHeld("partition ledger device differs")
            with _open(path) as db:
                if not _table(db,"manifest_write_identity"):raise StorageHeld("partition identity missing")
                row=db.execute("SELECT owner,epoch,lane FROM manifest_write_identity WHERE singleton=1").fetchone()
                if row is None or tuple(row)!=(self.owner,self.epoch,lane):
                    raise StorageHeld("partition identity differs")
            # Refuse missing partitions; ManifestArchive normally initializes
            # a missing file, so verify before and immediately after opening.
            result=ManifestArchive(path,PartitionBulk(self.legacy.bulk,self.owner,_namespace(self.epoch,lane)),create=False)
            if _private(path)[1]!=identity:raise StorageHeld("partition file replaced")
            return result
        except (ShardHeld,OSError) as exc:raise StorageHeld("manifest write lane held") from exc

    def for_id(self,identifier):
        return self.archive(self._lane(identifier))

    def begin(self,**kwargs):
        return self.for_id(self.identifier(kwargs["logical_key"],kwargs["operation"])).begin(self.scope,**kwargs)

    def abort_intent(self,**kwargs):
        return self.for_id(self.identifier(kwargs["logical_key"],kwargs["operation"])).abort_intent(self.scope,**kwargs)

    def history(self,logical_key,*,limit=32,before=None):
        if type(limit) is not int or not 1<=limit<=128:raise ValueError("history bound")
        pages=[self.archive(i).history(self.scope,logical_key,limit=limit,before=before)
               for i in range(LANES if self.enabled else 1)]
        rows=[r for page in pages for r in page["manifests"]]
        if len({r["id"] for r in rows})!=len(rows):raise StorageHeld("duplicate manifest history identity")
        rows.sort(key=lambda r:(r["created_at"],r["id"]),reverse=True)
        more=len(rows)>limit or any(page["next_cursor"] is not None for page in pages)
        result=rows[:limit]
        return {"manifests":result,"next_cursor":[result[-1]["created_at"],result[-1]["id"]] if more and result else None,
                "partitioned":self.enabled,"snapshot_consistent":False}

    def usage(self):
        if not self.enabled:return self.legacy.usage(self.scope)
        totals={"manifests":{},"unique_chunks":0,"unique_raw_bytes":0,"unique_compressed_bytes":0,
                "capacity_guaranteed":False,"chunk_counts_are_namespace_local":True,"write_lanes":LANES}
        for i in range(LANES):
            usage=self.archive(i).usage(self.scope)
            for state,count in usage["manifests"].items():totals["manifests"][state]=totals["manifests"].get(state,0)+count
            for key in ("unique_chunks","unique_raw_bytes","unique_compressed_bytes"):totals[key]+=usage[key]
        return totals

    def collect(self,*,limit=32):
        if not self.enabled:return self.legacy.collect(self.scope,limit=limit)
        if type(limit) is not int or not 1<=limit<=128:raise ValueError("collection bound")
        # Persist only a cursor, never a second reference count. Per-call
        # work is bounded by limit plus at most nine empty lane probes.
        with _open(self.legacy.path) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("SELECT next_collect FROM manifest_write_enrollment WHERE owner=? AND epoch=?",(self.owner,self.epoch)).fetchone()
                if row is None:raise StorageHeld("collection enrollment changed")
                start=row[0]
                db.execute("UPDATE manifest_write_enrollment SET next_collect=? WHERE owner=? AND epoch=?",
                           ((start+1)%LANES,self.owner,self.epoch))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        collected=0
        for offset in range(LANES):
            if collected>=limit:break
            collected+=self.archive((start+offset)%LANES).collect(self.scope,limit=limit-collected)["collected"]
        return {"collected":collected,"physical_secure_erasure":False}


def main():
    import argparse
    from core.dragon_hoarder_copy import _archive
    from core.dragon_hoarder_qualification import open_backup
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy",choices=("primary","backup"),required=True)
    parser.add_argument("--scope-json",required=True)
    parser.add_argument("--offline-writers-stopped",action="store_true")
    args=parser.parse_args()
    if not args.offline_writers_stopped:parser.error("all writers must be stopped")
    path,_=_private(Path(args.scope_json))
    if path.stat().st_size>4096:raise StorageHeld("scope file bound")
    scope=json.loads(path.read_bytes())
    archive=_archive() if args.copy=="primary" else open_backup()
    owner=archive._owner(scope)
    print(json.dumps(provision(owner.path,scope,offline_acknowledged=True),sort_keys=True))


if __name__=="__main__":main()
