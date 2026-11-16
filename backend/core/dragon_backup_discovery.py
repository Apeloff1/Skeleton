"""Exhaustive file discovery within explicit private application roots.

No home-directory sweep, credential extraction, symlink following or remote
inventory. Reports contain private relative file names and SHA-256 witnesses,
not contents. Stop writers for an authoritative snapshot. A root catalogue
cannot prove that there are no undeclared application or external stores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from core.dragon_mongo_receipt import _read_json
from core.dragon_graph_deployment import _dir,_json,_sync_dir,DeploymentHeld
from core.dragon_owner_shards import _private,_open

SCHEMA="skeleton.dragon.application-root-inventory.v1"
MAX_ROOTS=64
MAX_FILES=1_000_000
MAX_BYTES=64*1024**4
MAX_DEPTH=64
MAX_CHILDREN=65_536
PLANES={"source","configuration","user_files","models","assets","local_database",
        "mongo_exports","external_exports","runtime_state","unclassified"}
REQUIRED=PLANES-{"unclassified"}


def _plan(doc):
    if (not isinstance(doc,dict) or set(doc)!={"schema","roots"} or doc["schema"]!=SCHEMA
            or not isinstance(doc["roots"],list) or not 1<=len(doc["roots"])<=MAX_ROOTS):
        raise ValueError("explicit application root catalogue required")
    paths=[];labels=set()
    for item in doc["roots"]:
        if (not isinstance(item,dict) or set(item)!={"id","plane","path"}
                or not isinstance(item["id"],str) or not 1<=len(item["id"])<=64
                or not item["id"].isascii() or not item["id"].replace("-","").replace("_","").isalnum()
                or item["id"] in labels or item["plane"] not in PLANES
                or not isinstance(item["path"],str)):
            raise ValueError("invalid root identity")
        root=_dir(Path(item["path"]))
        if root.resolve(strict=True)!=root or any(root==p or root.is_relative_to(p) or p.is_relative_to(root) for p in paths):
            raise ValueError("overlapping or noncanonical inventory roots")
        labels.add(item["id"]);paths.append(root)
    return [(x,Path(x["path"])) for x in doc["roots"]]


def _witness(st):
    return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns,st.st_mode)


def _file_hash(path,root):
    if path.resolve(strict=True)!=path or not path.is_relative_to(root):
        raise DeploymentHeld("inventory path escaped")
    before=path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<=before.st_size<=MAX_BYTES:
        raise DeploymentHeld("unsupported inventory object")
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
    try:
        if _witness(os.fstat(fd))!=_witness(before):raise DeploymentHeld("inventory object changed")
        h=hashlib.sha256();count=0
        with os.fdopen(fd,"rb") as stream:
            fd=-1
            for block in iter(lambda:stream.read(1024*1024),b""):
                count+=len(block);h.update(block)
            if _witness(os.fstat(stream.fileno()))!=_witness(before):
                raise DeploymentHeld("inventory object changed during read")
    finally:
        if fd!=-1:os.close(fd)
    if count!=before.st_size or _witness(path.lstat())!=_witness(before):
        raise DeploymentHeld("inventory object readback differs")
    return count,h.hexdigest()


def _walk(root):
    def visit(folder,depth):
        if depth>MAX_DEPTH:raise DeploymentHeld("inventory depth cap")
        before=folder.lstat()
        if not stat.S_ISDIR(before.st_mode) or folder.resolve(strict=True)!=folder:
            raise DeploymentHeld("inventory directory changed")
        with os.scandir(folder) as scan:
            entries=[]
            for entry in scan:
                if len(entries)>=MAX_CHILDREN:raise DeploymentHeld("inventory directory entry cap")
                entries.append(entry.name)
        for name in sorted(entries):
            child=folder/name;info=child.lstat()
            relative=child.relative_to(root).as_posix()
            if len(relative.encode("utf-8"))>4096:raise DeploymentHeld("inventory path bound")
            mode=stat.S_IMODE(info.st_mode)
            if stat.S_ISDIR(info.st_mode):
                yield relative,"directory",mode,0,hashlib.sha256(b"directory").hexdigest()
                yield from visit(child,depth+1)
            elif stat.S_ISREG(info.st_mode):
                size,h=_file_hash(child,root)
                if _witness(child.lstat())!=_witness(info):raise DeploymentHeld("inventory metadata changed")
                yield relative,"file",mode,size,h
            else:raise DeploymentHeld("symlink, device or other special object requires explicit review")
        if _witness(folder.lstat())!=_witness(before):raise DeploymentHeld("inventory directory changed during scan")
    yield from visit(root,0)


def discover(plan_path,ledger,*,expected_plan_sha,offline_acknowledged):
    if offline_acknowledged is not True:raise ValueError("stop all application writers before discovery")
    plan_path=Path(plan_path);ledger=Path(ledger)
    doc=_read_json(plan_path)
    plan_sha=hashlib.sha256(_json(doc)).hexdigest()
    if expected_plan_sha!=plan_sha:raise ValueError("root catalogue digest differs")
    roots=_plan(doc)
    if any(ledger==root or ledger.is_relative_to(root) or plan_path.is_relative_to(root) for _,root in roots):
        raise ValueError("inventory control files must be outside scanned roots")
    _private(ledger,create=True)
    count=directories=total=0;chain="0"*64;summary=[]
    with _open(ledger) as db:
        db.executescript("""CREATE TABLE inventory(root TEXT NOT NULL,relative TEXT NOT NULL,kind TEXT NOT NULL,
            mode INTEGER NOT NULL,bytes INTEGER NOT NULL,sha256 TEXT NOT NULL,
            PRIMARY KEY(root,relative)) WITHOUT ROWID;
            CREATE TABLE publication(singleton INTEGER PRIMARY KEY CHECK(singleton=1),receipt TEXT NOT NULL);""")
        db.execute("BEGIN IMMEDIATE")
        for entry,root in sorted(roots,key=lambda x:x[0]["id"]):
            local_count=local_directories=local_bytes=0
            for relative,kind,mode,size,h in _walk(root):
                if kind=="file":count+=1;local_count+=1
                else:directories+=1;local_directories+=1
                total+=size;local_bytes+=size
                if count+directories>MAX_FILES or total>MAX_BYTES:raise DeploymentHeld("inventory ceiling; partition explicitly")
                db.execute("INSERT INTO inventory VALUES(?,?,?,?,?,?)",(entry["id"],relative,kind,mode,size,h))
                chain=hashlib.sha256(_json([chain,entry["id"],relative,kind,mode,size,h])).hexdigest()
            summary.append({"id":entry["id"],"plane":entry["plane"],"files":local_count,
                            "directories":local_directories,"bytes":local_bytes})
        if hashlib.sha256(_json(_read_json(plan_path))).hexdigest()!=plan_sha:
            raise DeploymentHeld("root catalogue changed")
        covered={r["plane"] for r in summary}
        result={"schema":SCHEMA,"plan_sha256":plan_sha,"inventory_digest":chain,
                "files":count,"directories":directories,"bytes":total,"roots":summary,
                "missing_planes":sorted(REQUIRED-covered),"unclassified_roots":sum(r["plane"]=="unclassified" for r in summary),
                "declared_roots_scanned":True,"all_application_roots_proven":False,
                "external_service_state_proven":False,"backup_created":False}
        db.execute("INSERT INTO publication VALUES(1,?)",(json.dumps(result,sort_keys=True),))
        db.execute("COMMIT")
    _sync_dir(ledger.parent)
    return result


def verify_mirror(ledger,plan_path,*,expected_inventory_digest,offline_acknowledged):
    """Verify a separately restored directory tree against every inventory row."""
    if offline_acknowledged is not True:raise ValueError("stop mirror writers before verification")
    roots=_plan(_read_json(Path(plan_path)))
    with _open(Path(ledger)) as db:
        db.execute("BEGIN")
        row=db.execute("SELECT receipt FROM publication WHERE singleton=1").fetchone()
        if row is None:raise DeploymentHeld("inventory not sealed")
        receipt=json.loads(row[0])
        if receipt["inventory_digest"]!=expected_inventory_digest:
            raise DeploymentHeld("inventory digest differs")
        expected={r["id"]:r["plane"] for r in receipt["roots"]}
        if {x["id"]:x["plane"] for x,_ in roots}!=expected:
            raise DeploymentHeld("mirror root catalogue differs")
        chain="0"*64;count=directories=total=0
        for entry,root in sorted(roots,key=lambda x:x[0]["id"]):
            local=0
            for relative,kind,mode,size,h in _walk(root):
                if kind=="file":count+=1
                else:directories+=1
                local+=1;total+=size
                if count+directories>MAX_FILES or total>MAX_BYTES:raise DeploymentHeld("mirror inventory ceiling")
                match=db.execute("SELECT kind,mode,bytes,sha256 FROM inventory WHERE root=? AND relative=?",
                                 (entry["id"],relative)).fetchone()
                if match is None or tuple(match)!=(kind,mode,size,h):
                    raise DeploymentHeld("mirror entry differs or is unexpected")
                chain=hashlib.sha256(_json([chain,entry["id"],relative,kind,mode,size,h])).hexdigest()
            if local!=db.execute("SELECT COUNT(*) FROM inventory WHERE root=?",(entry["id"],)).fetchone()[0]:
                raise DeploymentHeld("mirror files missing")
        if (chain,count,directories,total)!=(expected_inventory_digest,receipt["files"],receipt["directories"],receipt["bytes"]):
            raise DeploymentHeld("mirror aggregate differs")
    return {"inventory_digest":chain,"files":count,"directories":directories,"bytes":total,"declared_mirror_verified":True,
            "full_application_recovery_verified":False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ledger",required=True,type=Path);p.add_argument("--plan",required=True,type=Path)
    p.add_argument("--expected-digest",required=True);p.add_argument("--verify-mirror",action="store_true")
    p.add_argument("--offline-writers-stopped",action="store_true")
    a=p.parse_args(argv)
    if a.verify_mirror:
        result=verify_mirror(a.ledger,a.plan,expected_inventory_digest=a.expected_digest,
                             offline_acknowledged=a.offline_writers_stopped)
    else:result=discover(a.plan,a.ledger,expected_plan_sha=a.expected_digest,
                        offline_acknowledged=a.offline_writers_stopped)
    print(json.dumps(result,sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
