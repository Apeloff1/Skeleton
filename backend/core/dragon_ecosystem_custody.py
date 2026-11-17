"""Offline Dragon local storage inventory and complete-set custody export.

No live Mongo migration, automatic path switch, or destructive restore.
The operator must stop ALL writers across all planes for the entire export.
The catalogue is streamed to SQLite; payload bytes are never held in memory.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from core import dragon_graph_authority as graph
from core import dragon_graph_deployment as custody
from core.dragon_owner_shards import _private,_open,_table,shard_paths
from core.dragon_manifest_write_lanes import _file,_epoch
from core.dragon_storage_topology import topology_config
from core.dragon_hoarder_bulk import Volume,MAX_VOLUMES

MAX_FILES=1_000_000
DB_VARS={
    "knowledge":"SKL_DRAGON_KNOWLEDGE_DB_PATH",
    "practice":"SKL_DRAGON_PRACTICE_DB_PATH",
    "raw_export_custody":"SKL_DRAGON_RAW_EXPORT_DB_PATH",
    "export_jobs":"SKL_DRAGON_EXPORT_JOB_DB_PATH",
    "corpus":"SKL_DRAGON_GAME_CORPUS_DB_PATH",
    "primary_manifest":"SKL_DRAGON_HOARDER_MANIFEST_DB_PATH",
    "backup_manifest":"SKL_DRAGON_HOARDER_BACKUP_MANIFEST_PATH",
}
SCHEMA="""
CREATE TABLE files(
 id INTEGER PRIMARY KEY,plane TEXT NOT NULL,original TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL UNIQUE,bytes INTEGER NOT NULL,sha256 TEXT NOT NULL
);
CREATE TABLE publication(singleton INTEGER PRIMARY KEY CHECK(singleton=1),count INTEGER NOT NULL,
 bytes INTEGER NOT NULL,digest TEXT NOT NULL,scope TEXT NOT NULL);
"""


def manifest_paths(base):
    """Enumerate nested write-lane identities without initializing any store."""
    for path in shard_paths(Path(base),"manifest"):
        yield path
        with _open(path) as db:
            if not _table(db,"manifest_write_enrollment"):continue
            for owner,epoch in db.execute("SELECT owner,epoch FROM manifest_write_enrollment ORDER BY owner"):
                _epoch(owner);_epoch(epoch)
                for lane in range(1,10):
                    child,_=_private(_file(path,owner,epoch,lane))
                    with _open(child) as part:
                        row=part.execute("SELECT owner,epoch,lane FROM manifest_write_identity WHERE singleton=1").fetchone()
                        if not row or tuple(row)!=(owner,epoch,lane):raise custody.DeploymentHeld("manifest lane marker differs")
                    if child.stat().st_dev!=path.stat().st_dev:raise custody.DeploymentHeld("manifest lane device differs")
                    yield child


def _volume_paths(variable):
    raw=topology_config(variable)
    if not raw:return
    specs=json.loads(raw)
    if not isinstance(specs,list) or not 1<=len(specs)<=MAX_VOLUMES:raise ValueError("payload configuration bound")
    names=set();devices=set()
    for spec in specs:
        if not isinstance(spec,dict) or not {"name","root","payload_budget"}<=set(spec) or set(spec)-{"name","root","payload_budget","free_reserve"}:
            raise ValueError("payload configuration shape")
        vol=Volume(**{**spec,"root":Path(spec["root"])})
        dev=vol.root.stat().st_dev
        if vol.name in names or dev in devices:raise custody.DeploymentHeld("duplicate volume or device")
        names.add(vol.name);devices.add(dev)
        path,_=_private(vol.root/"hoarder-payload-v1.sqlite3")
        with _open(path) as db:
            row=db.execute("SELECT name FROM volume_identity WHERE singleton=1").fetchone()
            if not row or row[0]!=vol.name:raise custody.DeploymentHeld("payload identity differs")
        yield path


def inventory():
    """Discover only configured, known local Dragon stores. Never scan home."""
    for plane,var in DB_VARS.items():
        raw=os.getenv(var,"").strip()
        if not raw:continue
        base,_=_private(Path(raw))
        if plane=="corpus":
            for path in shard_paths(base,"corpus"):
                yield "corpus",path
                with _open(path) as db:
                    if graph.active(db):
                        layout=graph._layout(db,path)
                        graph.attach(db,path)
                        for child in layout["paths"]:yield "graph",Path(child)
        elif plane.endswith("_manifest"):
            for path in manifest_paths(base):yield plane,path
        else:yield plane,base
    for plane,var in (("primary_payload","SKL_DRAGON_HOARDER_VOLUMES_JSON"),
                      ("backup_payload","SKL_DRAGON_HOARDER_BACKUP_VOLUMES_JSON")):
        if bool(os.getenv(DB_VARS[plane.replace("payload","manifest")],"").strip())!=bool(topology_config(var)):
            raise custody.DeploymentHeld("manifest and payload configuration must be paired")
        for path in _volume_paths(var):yield plane,path
    raw=os.getenv("SKL_DRAGON_DATASET_ROOT","").strip()
    if raw:
        from core.dragon_game_datasets import SHARDS,BASE_SHARDS,shard_path
        root=custody._dir(Path(raw))
        for index in range(SHARDS):
            path=shard_path(root,index)
            if not path.exists() and not path.is_symlink():
                if any(s.exists() or s.is_symlink() for s in custody._sidecars(path)):
                    raise custody.DeploymentHeld("dataset missing with sidecar")
                continue
            path,_=_private(path)
            if index>=BASE_SHARDS:_private(shard_path(root,index%BASE_SHARDS))
            if index<BASE_SHARDS:
                with _open(path) as db:
                    if _table(db,"dataset_game_routes"):
                        for lane, in db.execute("SELECT DISTINCT lane FROM dataset_game_routes"):
                            if not 0<=lane<SHARDS//BASE_SHARDS:raise custody.DeploymentHeld("dataset route invalid")
                            _private(shard_path(root,index+lane*BASE_SHARDS))
            yield "dataset",path


def _enumerate():
    entries=[];seen=set()
    for plane,path in inventory():
        path,identity=_private(path)
        if identity in seen:raise custody.DeploymentHeld("storage files alias")
        seen.add(identity);entries.append((plane,path))
        if len(entries)>MAX_FILES:raise custody.DeploymentHeld("inventory limit")
    if not entries:raise custody.DeploymentHeld("no configured local storage")
    return sorted(entries,key=lambda row:(row[0],str(row[1])))


@contextmanager
def _checkpoint(path):
    with _open(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]!=0:
            raise custody.DeploymentHeld("database checkpoint busy")
        if db.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower()!="delete":
            raise custody.DeploymentHeld("rollback journal conversion failed")
        db.execute("PRAGMA synchronous=EXTRA")
        db.execute("BEGIN EXCLUSIVE")
        try:
            custody._quick(db)
            if any(s.exists() or s.is_symlink() for s in custody._sidecars(path)):
                raise custody.DeploymentHeld("database sidecar remains")
            yield
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise


def _witness(rows):
    digest=hashlib.sha256();count=total=0
    for row in rows:
        raw=custody._json(list(row));digest.update(len(raw).to_bytes(8,"big"));digest.update(raw)
        total+=row[4];count+=1
    return count,total,digest.hexdigest()


def export(destination,*,offline_acknowledged=False):
    custody._ack(offline_acknowledged)
    dest=Path(destination);entries=_enumerate()
    for plane,path in entries:
        if plane=="corpus":
            with _open(path) as db:active=graph.active(db)
            if active:graph.qualify(path,full=True)
    custody._require_space([(dest.parent,sum(p.stat().st_size for _,p in entries))])
    custody._dir(dest,create=True)
    catalogue=dest/"catalogue.sqlite3";_private(catalogue,create=True)
    with _open(catalogue) as db:
        db.executescript(SCHEMA)
        for i,(plane,path) in enumerate(entries,1):
            # Bounded directory fanout; identifiers are deterministic and
            # never derived from potentially hostile absolute source names.
            folder=dest/("pack-"+str(i//1024))
            if not folder.exists():custody._dir(folder,create=True)
            name=folder.name+"/"+str(i)+".sqlite3"
            with _checkpoint(path):
                custody._require_space([(folder,path.stat().st_size)])
                witness=custody._copy(path,dest/name)
            db.execute("INSERT INTO files VALUES(?,?,?,?,?,?)",(i,plane,str(path),name,witness["bytes"],witness["sha256"]))
        # Re-enumerate and rehash every source before publishing. This detects
        # many accidental writer changes but does not replace a real stop.
        if _enumerate()!=entries:raise custody.DeploymentHeld("source topology changed")
        for row in db.execute("SELECT original,bytes,sha256 FROM files ORDER BY id"):
            if custody._fingerprint(Path(row[0]))!={"bytes":row[1],"sha256":row[2]}:
                raise custody.DeploymentHeld("source changed during offline copy")
        count,size,digest=_witness(db.execute("SELECT * FROM files ORDER BY id"))
        db.execute("INSERT INTO publication VALUES(1,?,?,?,'dragon-local-configured')",(count,size,digest))
    custody._sync_dir(dest);custody._sync_dir(dest.parent)
    return verify(dest)


def verify(destination):
    dest=custody._dir(Path(destination));catalogue,_=_private(dest/"catalogue.sqlite3")
    db=sqlite3.connect(catalogue.as_uri()+"?mode=ro&immutable=1",uri=True)
    try:
        custody._quick(db)
        publication=db.execute("SELECT count,bytes,digest,scope FROM publication WHERE singleton=1").fetchone()
        if not publication or not 1<=publication[0]<=MAX_FILES or publication[3]!="dragon-local-configured":
            raise custody.DeploymentHeld("backup not published")
        if _witness(db.execute("SELECT * FROM files ORDER BY id"))!=publication[:3]:
            raise custody.DeploymentHeld("inventory witness differs")
        counts={}
        for i,plane,original,name,size,digest in db.execute("SELECT * FROM files ORDER BY id"):
            if name!="pack-"+str(i//1024)+"/"+str(i)+".sqlite3" or not Path(original).is_absolute():
                raise custody.DeploymentHeld("backup path witness differs")
            target=dest/name
            if custody._fingerprint(target)!={"bytes":size,"sha256":digest}:
                raise custody.DeploymentHeld("backup file differs")
            if any(s.exists() or s.is_symlink() for s in custody._sidecars(target)):
                raise custody.DeploymentHeld("backup sidecar")
            read=sqlite3.connect(target.as_uri()+"?mode=ro&immutable=1",uri=True)
            try:custody._quick(read)
            finally:read.close()
            counts[plane]=counts.get(plane,0)+1
        return {"files":publication[0],"bytes":publication[1],"inventory_sha256":publication[2],"planes":counts,
                "verified":True,"mongo_included":False,"derived_indexes_included":False,
                "application_launch_verified":False,"physical_capacity_verified":False}
    finally:db.close()


def audit_payloads(destination):
    """Stream every sealed manifest from copied payloads; at most eight open volume databases."""
    from collections import OrderedDict
    from core.dragon_hoarder_bulk import BulkArchive,owner_key,_storage_owner
    from core.dragon_manifest_write_lanes import _namespace
    from core.dragon_hoarder_manifests import BLOCK
    from core.dragon_content_chunks import decode_layout
    receipt=verify(destination);dest=Path(destination)
    index=sqlite3.connect((dest/"catalogue.sqlite3").as_uri()+"?mode=ro&immutable=1",uri=True)
    volumes={};cache=OrderedDict();count=chunks=total=0
    def connect(path):
        db=sqlite3.connect(path.as_uri()+"?mode=ro&immutable=1",uri=True);db.row_factory=sqlite3.Row
        return db
    def payload(plane,name):
        key=(plane,name)
        if key not in volumes:raise custody.DeploymentHeld("manifest volume not in export")
        if key in cache:
            cache.move_to_end(key);return cache[key]
        if len(cache)>=8:
            _,old=cache.popitem(last=False);old.close()
        db=connect(volumes[key]);cache[key]=db
        return db
    try:
        for plane,name in index.execute("SELECT plane,name FROM files WHERE plane IN ('primary_payload','backup_payload')"):
            path=dest/name;db=connect(path)
            try:
                marker=db.execute("SELECT name FROM volume_identity WHERE singleton=1").fetchone()
                if not marker or (plane,marker[0]) in volumes:raise custody.DeploymentHeld("payload volume marker differs")
                stats=db.execute("SELECT COUNT(*),COALESCE(SUM(compressed_bytes),0) FROM objects").fetchone()
                usage=db.execute("SELECT objects,payload_bytes FROM usage WHERE singleton=1").fetchone()
                if not usage or tuple(stats)!=tuple(usage):raise custody.DeploymentHeld("payload usage witness differs")
                volumes[plane,marker[0]]=path
            finally:db.close()
        for plane,name in index.execute("SELECT plane,name FROM files WHERE plane IN ('primary_manifest','backup_manifest') ORDER BY id"):
            db=connect(dest/name)
            try:
                lane=None
                if _table(db,"manifest_write_identity"):
                    lane=db.execute("SELECT owner,epoch,lane FROM manifest_write_identity WHERE singleton=1").fetchone()
                    if lane is None:raise custody.DeploymentHeld("manifest partition marker missing")
                if not _table(db,"manifests"):continue
                for row in db.execute("SELECT owner,id,scope_json,expected_hash,expected_bytes FROM manifests WHERE state='sealed' ORDER BY owner,id"):
                    scope=json.loads(row["scope_json"])
                    if owner_key(scope)!=row["owner"] or lane is not None and lane["owner"]!=row["owner"]:
                        raise custody.DeploymentHeld("manifest scope differs")
                    physical=_storage_owner(scope,_namespace(lane["epoch"],lane["lane"]) if lane else None)
                    layout=None
                    if _table(db,"manifest_layouts"):
                        entry=db.execute("SELECT lengths,witness FROM manifest_layouts WHERE owner=? AND manifest=?",
                            (row["owner"],row["id"])).fetchone()
                        if entry is not None:
                            try:layout=decode_layout(entry["lengths"],entry["witness"],row["expected_bytes"])
                            except ValueError as exc:raise custody.DeploymentHeld("manifest layout invalid") from exc
                    h=hashlib.sha256();size=ordinal=0
                    for part in db.execute("""SELECT p.ordinal,c.digest,c.volume,c.raw_bytes,c.compressed_bytes
                        FROM placements p JOIN chunks c ON c.owner=p.owner AND c.digest=p.digest
                        WHERE p.owner=? AND p.manifest=? ORDER BY p.ordinal""",(row["owner"],row["id"])):
                        expected=(layout[ordinal] if ordinal<len(layout) else 0) if layout is not None else min(BLOCK,row["expected_bytes"]-size)
                        if expected<=0 or part["ordinal"]!=ordinal or part["raw_bytes"]!=expected or part["compressed_bytes"] is None:
                            raise custody.DeploymentHeld("sealed chunk ordering or size differs")
                        stored=payload(plane.replace("manifest","payload"),part["volume"]).execute(
                            "SELECT raw_bytes,compressed_bytes,payload FROM objects WHERE owner=? AND digest=?",
                            (physical,part["digest"])).fetchone()
                        if not stored or stored[0]!=expected or stored[1]!=part["compressed_bytes"] or len(stored[2])!=stored[1]:
                            raise custody.DeploymentHeld("sealed payload receipt differs")
                        raw=BulkArchive._decode(stored[2],expected,part["digest"])
                        h.update(raw);size+=len(raw);ordinal+=1;chunks+=1
                    if (size!=row["expected_bytes"] or h.hexdigest()!=row["expected_hash"]
                            or layout is not None and ordinal!=len(layout)):
                        raise custody.DeploymentHeld("sealed manifest content witness differs")
                    total+=size;count+=1
            finally:db.close()
        return {**receipt,"sealed_manifests_verified":count,"chunk_references_verified":chunks,
                "decoded_bytes_verified":total,"building_and_aborted_verified":False,
                "sealed_payload_integrity_verified":True,"source_authorized":False}
    finally:
        for db in cache.values():db.close()
        index.close()


def restore_new(destination,*,offline_acknowledged=False):
    """Restore configured originals only; never replace existing bytes.

    All source files must be available in a verified package. A partially
    restored set is NOT a launchable deployment. Restore payload and graph
    children before their manifest/corpus metadata, while writers stay off.
    """
    custody._ack(offline_acknowledged);receipt=verify(destination)
    dest=custody._dir(Path(destination));catalogue,_=_private(dest/"catalogue.sqlite3")
    db=sqlite3.connect(catalogue.as_uri()+"?mode=ro&immutable=1",uri=True)
    try:
        requests={}
        for original,size,digest in db.execute("SELECT original,bytes,sha256 FROM files"):
            target=Path(original)
            if target.exists() or target.is_symlink():
                if custody._fingerprint(target)!={"bytes":size,"sha256":digest}:
                    raise custody.DeploymentHeld("existing original differs")
                if any(s.exists() or s.is_symlink() for s in custody._sidecars(target)):
                    raise custody.DeploymentHeld("existing original has sidecars")
            else:
                custody._unused(target)
                requests[target.parent]=requests.get(target.parent,0)+size
        custody._require_space(list(requests.items()))
        copied=0
        order="""SELECT original,name,bytes,sha256 FROM files ORDER BY
            CASE plane WHEN 'primary_payload' THEN 0 WHEN 'backup_payload' THEN 0
                       WHEN 'graph' THEN 1 WHEN 'dataset' THEN 2
                       WHEN 'primary_manifest' THEN 3 WHEN 'backup_manifest' THEN 3
                       WHEN 'corpus' THEN 4 ELSE 5 END,id"""
        for original,name,size,digest in db.execute(order):
            target=Path(original);witness={"bytes":size,"sha256":digest}
            if not target.exists():
                custody._publish_copy(dest/name,target,witness);copied+=1
            if custody._fingerprint(target)!=witness:raise custody.DeploymentHeld("restore witness differs")
        for original,size,digest in db.execute("SELECT original,bytes,sha256 FROM files"):
            if custody._fingerprint(Path(original))!={"bytes":size,"sha256":digest}:
                raise custody.DeploymentHeld("complete restore differs")
        return {**receipt,"restored":True,"new_files":copied,"configuration_changed":False,
                "application_launch_verified":False}
    finally:db.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("export");a.add_argument("--destination",required=True);a.add_argument("--offline-writers-stopped",action="store_true")
    v=sub.add_parser("verify");v.add_argument("--destination",required=True)
    q=sub.add_parser("audit-payloads");q.add_argument("--destination",required=True)
    r=sub.add_parser("restore-new");r.add_argument("--destination",required=True);r.add_argument("--offline-writers-stopped",action="store_true")
    args=p.parse_args()
    if args.command=="export":answer=export(args.destination,offline_acknowledged=args.offline_writers_stopped)
    elif args.command=="audit-payloads":answer=audit_payloads(args.destination)
    elif args.command=="restore-new":answer=restore_new(args.destination,offline_acknowledged=args.offline_writers_stopped)
    else:answer=verify(args.destination)
    print(json.dumps(answer,sort_keys=True))


if __name__=="__main__":main()
