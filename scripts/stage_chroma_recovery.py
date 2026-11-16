#!/usr/bin/env python3
"""Independently authorized non-destructive Chroma recovery staging.

Chooses exactly one of the already backed-up historical stores, verifies the
entire backup and independently approved exact manifest, copies only the
selected bytes into a NEW private directory, and checks SQLite integrity on
that private copy. No Docker, network, merge of stores, live restoration,
automatic repair, credential access, or deletion of source evidence.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, fields
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from scripts.chroma_backup import (
    BackupRejected, SCHEMA as BACKUP_SCHEMA, MAX_FILES, MAX_BYTES, MAX_MANIFEST_BYTES,
    _manifest_files, _publish_no_replace, verify_backup,
)

SCHEMA="skeleton.chroma.recovery-stage.v1"
_DOMAIN=b"skeleton.chroma.recovery-stage-approval.v1\0"
_SHA=re.compile(r"[0-9a-f]{40}\Z",re.ASCII)
_HEX=re.compile(r"[0-9a-f]{64}\Z",re.ASCII)
_ID=re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z",re.ASCII)
_MAX_APPROVAL=16384
_LANES=("container-data","legacy-volume")
_CHUNK=1024*1024
_MAX_LANE_PATH=4096
_MAX_DEPTH=48
_DB="chroma.sqlite3"
_REQUIRED_TABLES=frozenset(("collections","segments","embeddings"))


class RecoveryDenied(RuntimeError):
    """Source authority, custody or staged integrity is not qualified."""


def require(value,why="Chroma recovery staging denied"):
    if value is not True:
        raise RecoveryDenied(why)


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(",",":"),
                      allow_nan=False).encode("ascii")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest_pin(value):
    return type(value) is str and _HEX.fullmatch(value) is not None and value!="0"*64


def _unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,"duplicate custody document field")
        result[key]=value
    return result


def _constant(_):
    raise RecoveryDenied("nonfinite custody document")


def _json(raw,limit):
    require(type(raw) is bytes and 0<len(raw)<=limit,"invalid custody document size")
    try:
        result=json.loads(raw.decode("utf-8","strict"),object_pairs_hook=_unique,parse_constant=_constant)
        require(type(result) is dict,"invalid custody document")
        return result
    except (ValueError,UnicodeError,RecursionError,OverflowError):
        raise RecoveryDenied("unreadable custody document") from None


@dataclass(frozen=True,slots=True)
class StageApproval:
    authority_id: str
    deployment_id: str
    source_head: str
    backup_manifest_sha256: str
    selected_lane: str
    selected_inventory_sha256: str
    selection_review_sha256: str
    quiescence_review_sha256: str
    issued_at: int
    expires_at: int

    def __post_init__(self):
        require(all(type(v) is str and _ID.fullmatch(v) is not None
                    for v in (self.authority_id,self.deployment_id)))
        require(type(self.source_head) is str and _SHA.fullmatch(self.source_head) is not None
                and type(self.selected_lane) is str and self.selected_lane in _LANES)
        require(all(digest_pin(v) for v in (self.backup_manifest_sha256,
                    self.selected_inventory_sha256,self.selection_review_sha256,
                    self.quiescence_review_sha256)))
        require(type(self.issued_at) is int and type(self.expires_at) is int
                and 0<self.issued_at<self.expires_at<(1<<63)
                and self.expires_at-self.issued_at<=1800)

    def canonical_bytes(self):
        return _DOMAIN+canonical({f.name:getattr(self,f.name) for f in fields(self)})

    @classmethod
    def parse(cls,raw):
        row=_json(raw,_MAX_APPROVAL)
        require(set(row)=={f.name for f in fields(cls)},"incorrect stage approval schema")
        return cls(**row)


@dataclass(frozen=True,slots=True)
class VerifiedStageApproval:
    plan: StageApproval
    signature: bytes
    authority_id: str
    deployment_id: str
    source_head: str
    public_key: bytes

    def __post_init__(self):
        self.verify()

    def verify(self):
        p=self.plan
        require(type(p) is StageApproval and p.authority_id==self.authority_id
                and p.deployment_id==self.deployment_id and p.source_head==self.source_head
                and type(self.signature) is bytes and len(self.signature)==64
                and type(self.public_key) is bytes and len(self.public_key)==32
                and p.issued_at<=int(time.time())<p.expires_at)
        try:
            Ed25519PublicKey.from_public_bytes(self.public_key).verify(self.signature,p.canonical_bytes())
        except (InvalidSignature,ValueError,TypeError):
            raise RecoveryDenied("independent stage signature denied") from None


def _stamp(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_nlink)


def _dir_stamp(info):
    return (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode))


def _absolute(path):
    require(isinstance(path,Path) and path.is_absolute() and ".." not in path.parts,
            "absolute no-link custody path required")
    require(os.name=="posix" and hasattr(os,"O_NOFOLLOW"),
            "descriptor-relative POSIX recovery required")
    return path


@contextmanager
def open_directory(path,*,private=False):
    """Walk every component with O_NOFOLLOW; never cross a symlink."""
    path=_absolute(path)
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
    fd=os.open("/",flags)
    try:
        for part in path.parts[1:]:
            child=os.open(part,flags,dir_fd=fd)
            os.close(fd)
            fd=child
        before=os.fstat(fd)
        require(stat.S_ISDIR(before.st_mode),"custody directory unavailable")
        if private:
            require(before.st_uid==os.geteuid() and stat.S_IMODE(before.st_mode)==0o700,
                    "stage destination parent must be independently provisioned mode 0700")
        yield fd
        for_check=os.open("/",flags)
        try:
            for part in path.parts[1:]:
                child=os.open(part,flags,dir_fd=for_check)
                os.close(for_check)
                for_check=child
            require(_dir_stamp(os.fstat(for_check))==_dir_stamp(before),"custody directory replaced")
        finally:
            os.close(for_check)
    finally:
        os.close(fd)


def _relative(raw):
    require(type(raw) is str and 0<len(raw.encode("utf-8"))<=_MAX_LANE_PATH
            and "\\" not in raw and ":" not in raw and not any(ord(c)<32 or ord(c)==127 for c in raw))
    p=PurePosixPath(raw)
    require(not p.is_absolute() and p.as_posix()==raw and len(p.parts)<=_MAX_DEPTH
            and all(part not in ("",".","..") for part in p.parts))
    return p


@contextmanager
def _parent_fd(base,path):
    fd=os.dup(base)
    try:
        for portion in path.parts[:-1]:
            child=os.open(portion,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd)
            fd=child
        yield fd,path.name
    finally:
        os.close(fd)


@contextmanager
def _regular(base,relative,limit):
    with _parent_fd(base,relative) as (parent,name):
        flags=os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK
        fd=os.open(name,flags,dir_fd=parent)
        try:
            info=os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<=info.st_size<=limit
                    and _stamp(info)==_stamp(os.stat(name,dir_fd=parent,follow_symlinks=False)),
                    "source file not a stable bounded regular object")
            yield fd,info.st_size
            require(_stamp(info)==_stamp(os.fstat(fd))
                    and _stamp(info)==_stamp(os.stat(name,dir_fd=parent,follow_symlinks=False)),
                    "source file changed during staging")
        finally:
            os.close(fd)


def _read_at(base,relative,limit):
    with _regular(base,relative,limit) as (fd,size):
        chunks=[]
        remaining=size
        while remaining:
            block=os.read(fd,min(remaining,_CHUNK))
            require(bool(block),"custody file truncated")
            chunks.append(block)
            remaining-=len(block)
        require(not os.read(fd,1),"custody file grew")
        return b"".join(chunks)


def read_private_file(path,limit):
    path=_absolute(path)
    with open_directory(path.parent) as base:
        with _regular(base,PurePosixPath(path.name),limit) as (fd,size):
            info=os.fstat(fd)
            require(info.st_uid==os.geteuid() and not info.st_mode&0o022,
                    "approval files must be operator-controlled")
            raw=bytearray()
            while len(raw)<size:
                block=os.read(fd,min(size-len(raw),_CHUNK))
                require(bool(block),"approval file truncated")
                raw.extend(block)
            require(not os.read(fd,1),"approval file changed")
            return bytes(raw)


def lane_inventory(manifest,lane):
    require(lane in _LANES and type(manifest) is dict and manifest.get("schema")==BACKUP_SCHEMA
            and type(manifest.get("files")) is list and 0<len(manifest["files"])<=MAX_FILES)
    result=[]
    all_paths=set()
    total=0
    for entry in manifest["files"]:
        require(type(entry) is dict and set(entry)=={"path","bytes","sha256"}
                and type(entry["bytes"]) is int and 0<=entry["bytes"]<=MAX_BYTES
                and type(entry["sha256"]) is str and _HEX.fullmatch(entry["sha256"]) is not None)
        path=_relative(entry["path"])
        require(len(path.parts)>=2 and path.parts[0] in _LANES and str(path) not in all_paths,
                "backup contains duplicate or unexpected store path")
        all_paths.add(str(path))
        total+=entry["bytes"]
        require(total<=MAX_BYTES,"backup exceeds staging capacity")
        if path.parts[0]==lane:
            result.append({"path":PurePosixPath(*path.parts[1:]).as_posix(),
                           "bytes":entry["bytes"],"sha256":entry["sha256"]})
    result.sort(key=lambda row:row["path"])
    require(bool(result),"selected backup store is empty")
    selected={row["path"] for row in result}
    require(_DB in selected and not any(path.startswith(_DB+"/") for path in selected),
            "selected store has no canonical SQLite database")
    # immutable read may ignore a WAL or rollback journal. Never claim
    # integrity over a potentially different logical database generation.
    require(not any(path in selected for path in (_DB+"-wal",_DB+"-shm",_DB+"-journal")),
            "selected backup requires separately reviewed SQLite journal recovery")
    for path in selected:
        p=PurePosixPath(path)
        require(not any(parent.as_posix() in selected for parent in p.parents if str(parent)!="."),
                "file/directory collision in backup inventory")
    return result


def lane_sha(rows):
    return sha(b"skeleton.chroma.selected-store-inventory.v1\0"+canonical(rows))


def _backup_observation(backup,root_fd):
    raw=_read_at(root_fd,PurePosixPath("manifest.json"),MAX_MANIFEST_BYTES)
    manifest=_json(raw,MAX_MANIFEST_BYTES)
    report=verify_backup(backup)
    require(report.get("matches_manifest") is True,"complete backup did not verify")
    require(_read_at(root_fd,PurePosixPath("manifest.json"),MAX_MANIFEST_BYTES)==raw,
            "backup manifest changed during verification")
    return raw,manifest


def inspect_backup_candidates(backup):
    """Read-only, no recommendation or authority inferred from counts."""
    backup=_absolute(backup)
    with open_directory(backup) as fd:
        raw,manifest=_backup_observation(backup,fd)
        lanes={}
        for lane in _LANES:
            try:
                rows=lane_inventory(manifest,lane)
                lanes[lane]={"eligible_for_review":True,"files":len(rows),
                             "bytes":sum(row["bytes"] for row in rows),
                             "inventory_sha256":lane_sha(rows)}
            except RecoveryDenied:
                lanes[lane]={"eligible_for_review":False}
        return {"schema":"skeleton.chroma.recovery-candidates.v1",
                "backup_manifest_sha256":sha(raw),"lanes":lanes,
                "selection_authorized":False,"database_integrity_verified":False,
                "migration_complete":False}


def _copy_file(base,lane,row,stage):
    relative=_relative(row["path"])
    source=PurePosixPath(lane,*relative.parts)
    target=stage.joinpath(*relative.parts)
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    target_fd=None
    try:
        with _regular(base,source,row["bytes"]) as (fd,size):
            require(size==row["bytes"],"selected source size changed")
            target_fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
            h=hashlib.sha256()
            remaining=size
            while remaining:
                data=os.read(fd,min(remaining,_CHUNK))
                require(bool(data),"selected source truncated")
                remaining-=len(data)
                h.update(data)
                view=memoryview(data)
                while view:
                    count=os.write(target_fd,view)
                    require(count>0,"private stage copy incomplete")
                    view=view[count:]
            require(not os.read(fd,1) and h.hexdigest()==row["sha256"],
                    "selected source content changed")
            os.fsync(target_fd)
            require(os.fstat(target_fd).st_size==size,"private stage size mismatch")
    finally:
        if target_fd is not None:
            os.close(target_fd)


def _fsync_tree(root):
    for current,dirs,_ in os.walk(root,topdown=False,followlinks=False):
        with open_directory(Path(current)) as fd:
            os.fsync(fd)


def sqlite_integrity(database,*,timeout=180):
    """Read-only full SQLite and FK checks on private staged bytes only."""
    require(type(timeout) in (int,float) and 0<timeout<=300)
    require(database.is_file() and not database.is_symlink())
    deadline=time.monotonic()+timeout
    conn=None
    try:
        conn=sqlite3.connect(database.as_uri()+"?mode=ro&immutable=1",uri=True,timeout=1)
        conn.enable_load_extension(False)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA trusted_schema=OFF")
        conn.set_progress_handler(lambda:1 if time.monotonic()>deadline else 0,1000)
        integrity=conn.execute("PRAGMA integrity_check(1)").fetchall()
        require(integrity==[("ok",)],"staged SQLite failed integrity check")
        require(conn.execute("PRAGMA foreign_key_check").fetchone() is None,
                "staged SQLite failed foreign-key check")
        names={row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' LIMIT 4097")}
        require(len(names)<=4096 and _REQUIRED_TABLES.issubset(names),
                "staged SQLite does not have expected Chroma schema")
        # Read only cardinalities, never values/documents/metadata.
        counts={}
        for table in sorted(_REQUIRED_TABLES):
            row=conn.execute('SELECT count(*) FROM "'+table+'"').fetchone()
            require(type(row) is tuple and len(row)==1 and type(row[0]) is int and 0<=row[0]<(1<<63))
            counts[table]=row[0]
        return {"sqlite_integrity_check":True,"foreign_key_check":True,
                "required_schema_tables":True,"row_counts":counts,
                "vector_graph_integrity_verified":False}
    except (sqlite3.Error,OSError,ValueError):
        raise RecoveryDenied("staged SQLite integrity unavailable") from None
    finally:
        if conn is not None:
            conn.close()


def _assert_head(expected):
    require(type(expected) is str and _SHA.fullmatch(expected) is not None)
    try:
        proc=subprocess.run(["git","-C",str(ROOT),"rev-parse","HEAD"],stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,timeout=10,check=True)
        require(proc.stdout.strip()==expected.encode("ascii"),"reviewed recovery source changed")
        proc=subprocess.run(["git","-C",str(ROOT),"diff","--quiet","--no-ext-diff","HEAD","--"],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=False)
        require(proc.returncode==0,"reviewed recovery tracked source changed")
    except (OSError,subprocess.SubprocessError):
        raise RecoveryDenied("reviewed recovery source unavailable") from None


def stage_recovery(backup,output,approval):
    """Publish new private stage after two exact backup checks and SQLite proof."""
    require(type(approval) is VerifiedStageApproval)
    approval.verify()
    plan=approval.plan
    _assert_head(plan.source_head)
    backup,output=_absolute(backup),_absolute(output)
    require(output!=backup and backup not in output.parents and output not in backup.parents
            and output!=ROOT and ROOT not in output.parents,"stage must be outside source backup and repository")
    require(not output.exists() and not output.is_symlink(),"stage destination already exists")
    with open_directory(backup) as base,open_directory(output.parent,private=True) as parent:
        raw,manifest=_backup_observation(backup,base)
        require(sha(raw)==plan.backup_manifest_sha256,"independent backup manifest pin mismatch")
        rows=lane_inventory(manifest,plan.selected_lane)
        require(lane_sha(rows)==plan.selected_inventory_sha256,"independent store inventory pin mismatch")
        with tempfile.TemporaryDirectory(prefix=".chroma-stage-",dir=output.parent) as temporary:
            stage=Path(temporary)
            stage.chmod(0o700)
            data=stage/"data"
            data.mkdir(mode=0o700)
            for row in rows:
                approval.verify()
                _copy_file(base,plan.selected_lane,row,data)
            require(_manifest_files(data)==rows,"private copy differs from signed inventory")
            integrity=sqlite_integrity(data/_DB)
            require(_manifest_files(data)==rows,"SQLite verification mutated staged bytes")
            final_raw,final_manifest=_backup_observation(backup,base)
            require(final_raw==raw and lane_inventory(final_manifest,plan.selected_lane)==rows,
                    "source backup changed while staging")
            _assert_head(plan.source_head)
            approval.verify()
            receipt={"schema":SCHEMA,"source_head":plan.source_head,
                "backup_manifest_sha256":plan.backup_manifest_sha256,
                "selected_lane":plan.selected_lane,"selected_inventory_sha256":plan.selected_inventory_sha256,
                "authority_key_sha256":sha(approval.public_key),"approval_sha256":sha(plan.canonical_bytes()),
                "selection_review_sha256":plan.selection_review_sha256,
                "quiescence_review_sha256":plan.quiescence_review_sha256,
                "integrity":integrity,"files":len(rows),"bytes":sum(row["bytes"] for row in rows),
                "live_store_modified":False,"migration_complete":False,"release_qualified":False}
            receipt["receipt_sha256"]=sha(b"skeleton.chroma.recovery-stage-receipt.v1\0"+canonical(receipt))
            with (stage/"receipt.json").open("xb") as stream:
                stream.write(canonical(receipt)+b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            _fsync_tree(stage)
            # Verify parent identity and preserve original destination, even
            # if another process creates it after our initial check.
            with open_directory(output.parent,private=True) as current:
                require(_dir_stamp(os.fstat(current))==_dir_stamp(os.fstat(parent)),
                        "stage destination parent replaced")
            approval.verify()
            _publish_no_replace(stage,output)
            os.fsync(parent)
            return receipt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup",type=Path,required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect-candidates",action="store_true")
    mode.add_argument("--output",type=Path)
    parser.add_argument("--plan",type=Path)
    parser.add_argument("--signature",type=Path)
    parser.add_argument("--authority")
    parser.add_argument("--deployment")
    parser.add_argument("--source-head")
    parser.add_argument("--operator-public-key-hex")
    args=parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.inspect_candidates:
            require(all(v is None for v in (args.plan,args.signature,args.authority,args.deployment,
                    args.source_head,args.operator_public_key_hex)),"inspection must not consume approval")
            result=inspect_backup_candidates(args.backup)
        else:
            require(args.plan is not None and args.signature is not None
                    and type(args.operator_public_key_hex) is str
                    and _HEX.fullmatch(args.operator_public_key_hex) is not None)
            plan=StageApproval.parse(read_private_file(args.plan,_MAX_APPROVAL))
            approval=VerifiedStageApproval(plan,read_private_file(args.signature,64),args.authority,
                args.deployment,args.source_head,bytes.fromhex(args.operator_public_key_hex))
            result=stage_recovery(args.backup,args.output,approval)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (RecoveryDenied,BackupRejected,OSError,ValueError,TypeError):
        print("Chroma recovery staging denied; no live restoration authorized.",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
