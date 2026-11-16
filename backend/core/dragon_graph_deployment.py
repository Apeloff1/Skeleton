"""Operator-controlled graph deployment, coherent backup and bounded device probes.

Requires a real stopped application and private local filesystems. Never
overwrites a database, auto-erases failed migration files, or claims that a
scratch benchmark establishes production capacity or power-loss safety.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import time

from core import dragon_graph_authority as graph
from core.dragon_owner_shards import _private,_open,guard_root,ShardHeld

BLOCK=1024*1024
RESERVE=512*BLOCK
MAX_MANIFEST=128*1024
MAX_BENCH_BYTES=256*BLOCK


class DeploymentHeld(RuntimeError):
    pass


def _ack(value):
    if value is not True:raise DeploymentHeld("stop all application and old writers; explicit acknowledgement required")


def _dir(path,*,create=False):
    path=Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path,*path.parents)):
        raise DeploymentHeld("absolute private directory required")
    if create:path.mkdir(mode=0o700,exist_ok=False)
    s=path.stat()
    if not stat.S_ISDIR(s.st_mode) or os.name=="posix" and (s.st_uid!=os.getuid() or s.st_mode&0o077):
        raise DeploymentHeld("private directory required")
    return path


def _sync_dir(path):
    # Windows directory fsync is not exposed by this Python API. Receipts
    # distinguish that limitation rather than promise physical durability.
    if os.name=="posix":
        fd=os.open(path,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
        try:os.fsync(fd)
        finally:os.close(fd)


def _json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(",",":"),allow_nan=False).encode()


def _new_json(path,value):
    raw=_json(value)
    if len(raw)>MAX_MANIFEST:raise DeploymentHeld("manifest size bound")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        with os.fdopen(fd,"wb") as out:
            fd=-1;out.write(raw);out.flush();os.fsync(out.fileno())
    finally:
        if fd!=-1:os.close(fd)
    _sync_dir(path.parent)


def _read_json(path):
    p,_=_private(path)
    with p.open("rb") as f:raw=f.read(MAX_MANIFEST+1)
    if len(raw)>MAX_MANIFEST:raise DeploymentHeld("manifest size bound")
    try:value=json.loads(raw)
    except (ValueError,UnicodeError) as exc:raise DeploymentHeld("manifest invalid") from exc
    if _json(value)!=raw:raise DeploymentHeld("manifest is not canonical")
    return value


def _sidecars(path):
    return tuple(Path(str(path)+s) for s in ("-wal","-shm","-journal"))


def _unused(path):
    _dir(path.parent)
    if path.exists() or path.is_symlink() or any(s.exists() or s.is_symlink() for s in _sidecars(path)):
        raise DeploymentHeld("destination or SQLite sidecar already exists")


def _fingerprint(path):
    path,identity=_private(path)
    h=hashlib.sha256();size=0
    with path.open("rb") as src:
        while chunk:=src.read(BLOCK):
            size+=len(chunk);h.update(chunk)
    if _private(path)[1]!=identity or path.stat().st_size!=size:
        raise DeploymentHeld("database changed during fingerprint")
    return {"bytes":size,"sha256":h.hexdigest()}


def _copy(source,target):
    source,identity=_private(source);_unused(target)
    h=hashlib.sha256();size=0
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        with source.open("rb") as inp,os.fdopen(fd,"wb") as out:
            fd=-1
            while chunk:=inp.read(BLOCK):
                size+=len(chunk);h.update(chunk);out.write(chunk)
            out.flush();os.fsync(out.fileno())
    finally:
        if fd!=-1:os.close(fd)
    _sync_dir(target.parent)
    witness={"bytes":size,"sha256":h.hexdigest()}
    if _private(source)[1]!=identity or source.stat().st_size!=size or _fingerprint(target)!=witness:
        raise DeploymentHeld("copied database readback differs")
    return witness


def _publish_copy(source,target,witness):
    """Stage a complete verified copy, then publish without an overwrite.

    A deterministic matching stage survives an interruption before publication.
    A crash between hard-link publication and unlinking the staging name
    deliberately holds for manual custody inspection of the two links.
    """
    _unused(target)
    stage=target.parent/("."+target.name+".dragon-restore-"+witness["sha256"][:24])
    if stage.exists() or stage.is_symlink():
        if _fingerprint(stage)!=witness:raise DeploymentHeld("partial staged restore differs")
    elif _copy(source,stage)!=witness:
        raise DeploymentHeld("restore staging witness differs")
    # link fails atomically if another process has created the destination.
    # This requires a local filesystem with hard-link support.
    if _fingerprint(stage)!=witness:raise DeploymentHeld("restore staging changed")
    os.link(stage,target,follow_symlinks=False)
    _sync_dir(target.parent)
    stage.unlink()
    _sync_dir(target.parent)
    if _fingerprint(target)!=witness:raise DeploymentHeld("published restore witness differs")


def _capacity(requests):
    """Aggregate required bytes by filesystem, not by logical lane."""
    devices={}
    for folder,needed in requests:
        folder=_dir(folder);dev=folder.stat().st_dev
        if type(needed) is not int or needed<0:raise ValueError("capacity request")
        entry=devices.setdefault(dev,{"representative":str(folder),"required_bytes":0,"free_bytes":shutil.disk_usage(folder).free})
        entry["required_bytes"]+=needed
        entry["free_bytes"]=min(entry["free_bytes"],shutil.disk_usage(folder).free)
    for dev,item in devices.items():
        item["device"]=dev
        item["reserve_bytes"]=RESERVE
        item["sufficient"]=item["free_bytes"]>=item["required_bytes"]+RESERVE
    return list(devices.values())


def _require_space(requests):
    report=_capacity(requests)
    if not all(row["sufficient"] for row in report):raise DeploymentHeld("insufficient device space including reserve")
    return report


def _quick(db,schema="main"):
    rows=db.execute("PRAGMA "+schema+".quick_check").fetchall()
    if len(rows)!=1 or rows[0][0]!="ok":raise DeploymentHeld("SQLite quick check failed")
    if db.execute("PRAGMA "+schema+".foreign_key_check").fetchone():raise DeploymentHeld("SQLite foreign key check failed")


@contextmanager
def _offline_snapshot(root):
    """Acquire an exclusive rollback-journal transaction across all graph files.

    Conversion of a legacy WAL root is intentionally done before copying.
    No graph rows are modified. Application-level writer stop is mandatory.
    """
    root,_=_private(root);guard_root(root,"corpus")
    with _open(root) as db:
        db.execute("PRAGMA foreign_keys=ON")
        active=graph.active(db);layout=graph._layout(db,root) if active else None
        paths=[root]+([Path(p) for p in layout["paths"]] if layout else [])
        if active:graph.attach(db,root)
        else:
            if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]!=0:
                raise DeploymentHeld("legacy WAL checkpoint busy")
            if db.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower()!="delete":
                raise DeploymentHeld("legacy journal conversion failed")
            db.execute("PRAGMA synchronous=EXTRA")
        db.execute("BEGIN EXCLUSIVE")
        try:
            _quick(db)
            if active:
                graph.read_fence(db)
                if db.execute("SELECT 1 FROM main.dragon_graph_probe LIMIT 1").fetchone():
                    raise DeploymentHeld("recover pending graph probe first")
                for index in range(graph.LANES):_quick(db,graph._alias(index))
                graph._verify_graph(db);graph._verify_directory(db)
                from core.dragon_graph_direct_writer import verify
                from core.dragon_graph_multi_batch import verify as verify_multi
                verify(db);verify_multi(db)
            if any(s.exists() or s.is_symlink() for p in paths for s in _sidecars(p)):
                raise DeploymentHeld("SQLite sidecar remains; no raw copy")
            yield paths,layout
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise


def backup(root,destination,*,offline_acknowledged=False):
    _ack(offline_acknowledged)
    root=Path(root);destination=Path(destination)
    _dir(destination.parent)
    with _offline_snapshot(root) as (paths,layout):
        _require_space([(destination.parent,sum(p.stat().st_size for p in paths))])
        _dir(destination,create=True)
        rows=[]
        for i,path in enumerate(paths):
            name="root.sqlite3" if i==0 else "lane-"+str(i-1)+".sqlite3"
            rows.append({"name":name,"original":str(path),**_copy(path,destination/name)})
        manifest={"version":1,"root":str(root),"epoch":layout["epoch"] if layout else None,
                  "files":rows,"directory_fsync":os.name=="posix",
                  "scope":"single_corpus_graph_root","external_payloads_included":False}
        _new_json(destination/"manifest.json",manifest)
        _sync_dir(destination.parent)
    return verify_backup(destination)


def _manifest(destination):
    destination=_dir(destination);m=_read_json(destination/"manifest.json")
    if not isinstance(m,dict) or set(m)!={"version","root","epoch","files","directory_fsync","scope","external_payloads_included"}:
        raise DeploymentHeld("backup manifest shape")
    if m["version"]!=1 or m["scope"]!="single_corpus_graph_root" or m["external_payloads_included"] is not False:
        raise DeploymentHeld("unsupported backup scope")
    epoch=m["epoch"];rows=m["files"]
    if epoch is not None and (not isinstance(epoch,str) or not graph.HEX.fullmatch(epoch)):raise DeploymentHeld("backup epoch")
    if not isinstance(rows,list) or len(rows)!=(graph.LANES+1 if epoch else 1):raise DeploymentHeld("backup file count")
    originals=set()
    for i,row in enumerate(rows):
        name="root.sqlite3" if i==0 else "lane-"+str(i-1)+".sqlite3"
        if (not isinstance(row,dict) or set(row)!={"name","original","bytes","sha256"} or row["name"]!=name
                or not isinstance(row["original"],str) or not Path(row["original"]).is_absolute()
                or row["original"] in originals or type(row["bytes"]) is not int or row["bytes"]<=0
                or not isinstance(row["sha256"],str) or not graph.HEX.fullmatch(row["sha256"])):
            raise DeploymentHeld("backup file witness")
        originals.add(row["original"])
    if rows[0]["original"]!=m["root"]:raise DeploymentHeld("backup root witness")
    return destination,m


def verify_backup(destination):
    destination,m=_manifest(destination)
    for i,row in enumerate(m["files"]):
        path=destination/row["name"]
        if _fingerprint(path)!={k:row[k] for k in ("bytes","sha256")}:raise DeploymentHeld("backup bytes differ")
        if any(s.exists() or s.is_symlink() for s in _sidecars(path)):raise DeploymentHeld("backup sidecar")
        db=sqlite3.connect(path.as_uri()+"?mode=ro&immutable=1",uri=True)
        try:
            _quick(db)
            if i==0 and m["epoch"]:
                value=json.loads(db.execute("SELECT layout FROM dragon_graph_authority WHERE singleton=1").fetchone()[0])
                if value.get("epoch")!=m["epoch"] or value.get("root")!=m["root"] or value.get("paths")!=[r["original"] for r in m["files"][1:]]:
                    raise DeploymentHeld("backup topology differs")
            elif i:
                marker=db.execute("SELECT epoch,lane FROM graph_identity WHERE singleton=1").fetchone()
                if marker!=(m["epoch"],i-1):raise DeploymentHeld("backup shard marker differs")
        finally:db.close()
    return {"manifest_sha256":hashlib.sha256(_json(m)).hexdigest(),"files":len(m["files"]),
            "bytes":sum(r["bytes"] for r in m["files"]),"root":m["root"],"epoch":m["epoch"],
            "hash_and_sqlite_verified":True,"external_payloads_included":False}


def restore_new(destination,*,offline_acknowledged=False):
    """Restore exact original paths only, with no overwrite and root last.

    Completed shard copies can be reused on retry if their hashes match.
    An interrupted partial copy or existing different database holds; never
    delete or overwrite it automatically. Keep the app stopped throughout.
    """
    _ack(offline_acknowledged);verified=verify_backup(destination)
    destination,m=_manifest(destination)
    rows=m["files"];root=Path(m["root"])
    # If root exists, only a complete exact replay is allowed. Never create a
    # missing graph shard behind an already published root.
    if root.exists() or root.is_symlink():
        for row in rows:
            p=Path(row["original"])
            if _fingerprint(p)!={k:row[k] for k in ("bytes","sha256")} or any(s.exists() or s.is_symlink() for s in _sidecars(p)):
                raise DeploymentHeld("existing root is not exact completed restore")
        return {**verified,"restored":True,"replayed":True}
    requests=[]
    for row in rows:
        p=Path(row["original"])
        if p.exists() or p.is_symlink():
            if _fingerprint(p)!={k:row[k] for k in ("bytes","sha256")} or any(s.exists() or s.is_symlink() for s in _sidecars(p)):
                raise DeploymentHeld("existing partial restore differs")
        else:
            _unused(p);requests.append((p.parent,row["bytes"]))
    _require_space(requests)
    for row in [*rows[1:],rows[0]]:
        p=Path(row["original"])
        if not p.exists():
            _publish_copy(destination/row["name"],p,{k:row[k] for k in ("bytes","sha256")})
    if m["epoch"]:graph.qualify(root,full=True)
    return {**verified,"restored":True,"replayed":False,"root_published_last":True}


def drill(destination,scratch,*,offline_acknowledged=False):
    """Disposable isolated verification clone; not a runnable application restore."""
    _ack(offline_acknowledged);receipt=verify_backup(destination)
    destination,m=_manifest(destination);scratch=Path(scratch)
    _dir(scratch.parent);_require_space([(scratch.parent,receipt["bytes"]*2)])
    _dir(scratch,create=True)
    for row in m["files"]:_copy(destination/row["name"],scratch/row["name"])
    root=scratch/"root.sqlite3"
    if m["epoch"]:
        with _open(root) as db:
            value=json.loads(db.execute("SELECT layout FROM dragon_graph_authority WHERE singleton=1").fetchone()[0])
            value["root"]=str(root);value["paths"]=[str(scratch/r["name"]) for r in m["files"][1:]]
            db.execute("UPDATE dragon_graph_authority SET layout=? WHERE singleton=1",(json.dumps(value,separators=(",",":")),))
        audit=graph.qualify(root,full=True)
        if audit["epoch"]!=m["epoch"]:raise DeploymentHeld("restore drill epoch differs")
    else:
        with _open(root) as db:_quick(db)
    return {**receipt,"isolated_restore_drill":True,"scratch":str(scratch),
            "full_graph_audit":bool(m["epoch"]),"power_loss_qualified":False,"app_launch_qualified":False}


def prepare(root,paths,workspace,*,offline_acknowledged=False):
    _ack(offline_acknowledged);root,_=_private(Path(root));paths=tuple(Path(p) for p in paths)
    if len(paths)!=graph.LANES or len(set(paths))!=graph.LANES or root in paths:raise ValueError("ten unique graph lane paths")
    workspace=Path(workspace);_dir(workspace.parent)
    with _open(root) as db:
        active=graph.active(db)
        if active and graph._layout(db,root)["paths"]!=[str(p) for p in paths]:raise DeploymentHeld("active graph topology differs")
    if not active:
        for p in paths:_unused(p)
    size=root.stat().st_size
    report=_require_space([(workspace.parent,size*2),(root.parent,size*3)]+[(p.parent,size*2) for p in paths])
    _dir(workspace,create=True)
    before=backup(root,workspace/"before",offline_acknowledged=True)
    plan={"version":1,"root":str(root),"paths":[str(p) for p in paths],
          "before_manifest_sha256":before["manifest_sha256"],"legacy":not active}
    _new_json(workspace/"deployment.json",plan)
    return {"prepared":True,"plan_sha256":hashlib.sha256(_json(plan)).hexdigest(),"backup":before,"device_preflight":report,
            "deployed":False}


def apply(workspace,*,offline_acknowledged=False):
    """Resume idempotent stages, retaining failed files and all backups."""
    _ack(offline_acknowledged);workspace=_dir(workspace);plan=_read_json(workspace/"deployment.json")
    if not isinstance(plan,dict) or set(plan)!={"version","root","paths","before_manifest_sha256","legacy"} or plan["version"]!=1:
        raise DeploymentHeld("deployment plan shape")
    receipt=verify_backup(workspace/"before")
    if receipt["manifest_sha256"]!=plan["before_manifest_sha256"] or receipt["root"]!=plan["root"]:
        raise DeploymentHeld("deployment preimage backup differs")
    root=Path(plan["root"]);paths=tuple(Path(x) for x in plan["paths"])
    if len(paths)!=graph.LANES or len(set(paths))!=graph.LANES or root in paths:raise DeploymentHeld("deployment paths differ")
    with _open(root) as db:active=graph.active(db)
    if not active:
        _,m=_manifest(workspace/"before")
        if not plan["legacy"] or _fingerprint(root)!={k:m["files"][0][k] for k in ("bytes","sha256")}:
            raise DeploymentHeld("legacy root changed since backup")
        for p in paths:_unused(p)
        _require_space([(root.parent,root.stat().st_size*3)]+[(p.parent,root.stat().st_size*2) for p in paths])
        graph.provision(root,paths,offline_acknowledged=True)
    with _open(root) as db:
        layout=graph._layout(db,root)
        if layout["paths"]!=list(plan["paths"]):raise DeploymentHeld("deployed graph topology differs")
    if receipt["epoch"] is not None and layout["epoch"]!=receipt["epoch"]:raise DeploymentHeld("source graph epoch changed")
    graph.qualify(root,full=True)
    from core.dragon_graph_direct_writer import install as review
    from core.dragon_graph_structural import install as structural
    from core.dragon_graph_multi_batch import install as multi
    from core.dragon_graph_owner_concurrency import install as same
    for stage in (review,structural,multi,same):stage(root,offline_acknowledged=True)
    audit=graph.qualify(root,full=True)
    result={"plan_sha256":hashlib.sha256(_json(plan)).hexdigest(),"epoch":audit["epoch"],
            "graph_migrated":True,"all_writer_modes_enabled":True,"full_graph_audit":True,
            "before_backup":receipt,"live_application_tested":False,"physical_capacity_verified":False}
    final=workspace/"deployment-receipt.json"
    if final.exists():
        if _read_json(final)!=result:raise DeploymentHeld("deployment receipt differs")
    else:_new_json(final,result)
    return result


def benchmark(root,*,bytes_per_lane=16*BLOCK,acknowledged=False):
    """Bounded actual non-sparse scratch I/O on each configured lane device."""
    if acknowledged is not True:raise DeploymentHeld("explicit scratch device write acknowledgement required")
    if type(bytes_per_lane) is not int or not BLOCK<=bytes_per_lane<=MAX_BENCH_BYTES:
        raise ValueError("benchmark bytes per lane")
    root,_=_private(Path(root))
    with _open(root) as db:
        if not graph.active(db):raise DeploymentHeld("graph topology not provisioned")
        layout=graph._layout(db,root)
    graph.qualify(root)
    paths=[_private(Path(p))[0] for p in layout["paths"]]
    space=_require_space([(p.parent,bytes_per_lane) for p in paths])
    import secrets
    nonce=secrets.token_hex(16)
    def run(item):
        i,path=item;target=path.parent/(".dragon-io-"+nonce+"-"+str(i))
        _unused(target)
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
        identity=_private(target)[1]
        h=hashlib.sha256();start=time.perf_counter()
        try:
            try:
                with os.fdopen(fd,"wb") as out:
                    fd=-1;left=bytes_per_lane
                    while left:
                        chunk=os.urandom(min(left,BLOCK));out.write(chunk);h.update(chunk);left-=len(chunk)
                    out.flush();os.fsync(out.fileno())
            finally:
                if fd!=-1:os.close(fd)
            write=max(time.perf_counter()-start,1e-9);start=time.perf_counter()
            actual=_fingerprint(target);read=max(time.perf_counter()-start,1e-9)
            if actual!={"bytes":bytes_per_lane,"sha256":h.hexdigest()}:
                raise DeploymentHeld("benchmark readback differs")
            return {"lane":i,"device":path.stat().st_dev,"bytes":bytes_per_lane,"sha256":h.hexdigest(),
                    "write_fsync_seconds":write,"read_hash_seconds":read,
                    "write_mib_s":bytes_per_lane/BLOCK/write,"read_mib_s":bytes_per_lane/BLOCK/read}
        finally:
            if _private(target)[1]!=identity:raise DeploymentHeld("scratch file replaced; cleanup held")
            target.unlink();_sync_dir(target.parent)
    start=time.perf_counter()
    with ThreadPoolExecutor(max_workers=4,thread_name_prefix="dragon-device") as pool:
        values=list(pool.map(run,enumerate(paths)))
    return {"epoch":layout["epoch"],"lanes":values,"elapsed_seconds":time.perf_counter()-start,
            "bytes_written_and_readback":sum(x["bytes"] for x in values),"devices":space,
            "bounded_scratch_io_verified":True,"maximum_capacity_verified":False,
            "graph_transaction_throughput_verified":False,"power_loss_qualified":False}


def transaction_probe(root,*,bytes_per_lane=64*1024,rounds=3,acknowledged=False):
    """Measure real fenced graph canary transactions, not game ingestion TPS."""
    if acknowledged is not True:raise DeploymentHeld("explicit graph device write acknowledgement required")
    if type(rounds) is not int or not 1<=rounds<=16 or type(bytes_per_lane) is not int or not 4096<=bytes_per_lane<=16*BLOCK:
        raise ValueError("transaction probe bounds")
    graph.qualify(Path(root))
    if graph.pending_probes(Path(root))["pending_probe_ids"]:
        raise DeploymentHeld("recover pending device probes first")
    results=[]
    for i in range(rounds):
        started=time.perf_counter()
        receipt=graph.write_probe(Path(root),bytes_per_lane=bytes_per_lane,acknowledged=True)
        elapsed=max(time.perf_counter()-started,1e-9)
        if not receipt.get("readback_verified") or not receipt.get("cleanup_verified"):
            raise DeploymentHeld("transaction probe receipt incomplete")
        results.append({"round":i,"seconds":elapsed,"verified_bytes":receipt["verified_bytes"],"probe_id":receipt["probe_id"]})
    if graph.pending_probes(Path(root))["pending_probe_ids"]:raise DeploymentHeld("graph probe cleanup incomplete")
    elapsed=sum(r["seconds"] for r in results)
    return {"rounds":results,"elapsed_seconds":elapsed,"verified_bytes":sum(r["verified_bytes"] for r in results),
            "probe_cycles_per_second":rounds/elapsed,"graph_canary_cycles_verified":True,
            "production_ingestion_throughput_verified":False,"maximum_capacity_verified":False,
            "power_loss_qualified":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="command",required=True)
    for name in ("backup","prepare","apply","restore-new","drill"):
        p=sub.add_parser(name);p.add_argument("--offline-writers-stopped",action="store_true")
        if name in ("backup","prepare"):p.add_argument("--root",required=True)
        if name in ("backup","restore-new","drill"):p.add_argument("--backup",required=True)
        if name in ("prepare","apply"):p.add_argument("--workspace",required=True)
        if name=="prepare":p.add_argument("paths",nargs=graph.LANES)
        if name=="drill":p.add_argument("--scratch",required=True)
    v=sub.add_parser("verify-backup");v.add_argument("--backup",required=True)
    b=sub.add_parser("benchmark");b.add_argument("--root",required=True)
    b.add_argument("--bytes-per-lane",type=int,default=16*BLOCK);b.add_argument("--acknowledge-device-writes",action="store_true")
    tx=sub.add_parser("transaction-probe");tx.add_argument("--root",required=True)
    tx.add_argument("--bytes-per-lane",type=int,default=64*1024);tx.add_argument("--rounds",type=int,default=3)
    tx.add_argument("--acknowledge-device-writes",action="store_true")
    args=parser.parse_args()
    if args.command=="transaction-probe":
        result=transaction_probe(args.root,bytes_per_lane=args.bytes_per_lane,rounds=args.rounds,acknowledged=args.acknowledge_device_writes)
    elif args.command=="verify-backup":result=verify_backup(args.backup)
    elif args.command=="benchmark":result=benchmark(args.root,bytes_per_lane=args.bytes_per_lane,acknowledged=args.acknowledge_device_writes)
    else:
        ack=args.offline_writers_stopped
        if args.command=="backup":result=backup(args.root,args.backup,offline_acknowledged=ack)
        elif args.command=="prepare":result=prepare(args.root,args.paths,args.workspace,offline_acknowledged=ack)
        elif args.command=="apply":result=apply(args.workspace,offline_acknowledged=ack)
        elif args.command=="restore-new":result=restore_new(args.backup,offline_acknowledged=ack)
        else:result=drill(args.backup,args.scratch,offline_acknowledged=ack)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":main()
