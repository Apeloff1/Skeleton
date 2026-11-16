"""Independent operator launch for protected canonical backend writers.

Run from a reviewed, clean project checkout with PYTHONPATH=.:backend.
This executable never migrates, generates an approval, writes an epoch or
activates guarded AI. A normal application boot is not the protected mode.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/"backend")]
from skeleton.app.canonical_writer_cutover import (
    CanonicalWriterCutover, VerifiedWriterCutover, WriterCutoverDenied,
    WriterDeploymentRetirement, inspect_writer_deployment, retire_writer_deployment,
)


def _file(path, bound):
    if not path.is_absolute() or os.name != "posix":
        raise WriterCutoverDenied("reviewed local cutover file required")
    fd = os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        def stamp(info):
            return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode
        if (not stat.S_ISREG(before.st_mode) or before.st_mode & 0o022
                or not 1 <= before.st_size <= bound or stamp(before) != stamp(path.lstat())):
            raise WriterCutoverDenied("reviewed local cutover file unavailable")
        result = bytearray()
        while len(result) < before.st_size:
            block = os.read(fd, min(65536, before.st_size-len(result)))
            if not block:
                raise WriterCutoverDenied("reviewed local cutover file changed")
            result.extend(block)
        if os.read(fd,1) or stamp(before) != stamp(os.fstat(fd)) or stamp(before) != stamp(path.lstat()):
            raise WriterCutoverDenied("reviewed local cutover file changed")
        return bytes(result)
    finally:
        os.close(fd)


def _private_state_directory(path):
    """Open an existing, independently provisioned POSIX custody directory.

    Follow no links at any path component; allow root-owned sticky ancestors
    (e.g. /tmp for tests), never an untrusted writable non-sticky ancestor.
    The leaf must belong to this service identity and be mode 0700.
    """
    if os.name != "posix" or not isinstance(path, Path) or not path.is_absolute():
        raise WriterCutoverDenied("protected local custody directory required")
    if path == Path("/") or ".." in path.parts:
        raise WriterCutoverDenied("invalid protected local custody directory")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for index, part in enumerate(path.parts[1:]):
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode):
                raise WriterCutoverDenied("invalid protected custody directory")
            if index == len(path.parts)-2:
                if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    raise WriterCutoverDenied("protected custody directory must be private")
            elif (info.st_uid not in (0, os.geteuid()) or
                  (info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX))):
                raise WriterCutoverDenied("untrusted protected custody ancestor")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _named_private_file(fd, name, directory_fd):
    actual = os.fstat(fd)
    named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if (not stat.S_ISREG(actual.st_mode) or actual.st_uid != os.geteuid()
            or stat.S_IMODE(actual.st_mode) != 0o600 or actual.st_nlink != 1
            or (actual.st_dev, actual.st_ino) != (named.st_dev, named.st_ino)):
        raise WriterCutoverDenied("protected local custody file identity invalid")


def _same_directory(path, fd):
    other = _private_state_directory(path)
    try:
        left, right = os.fstat(fd), os.fstat(other)
        if (left.st_dev, left.st_ino) != (right.st_dev, right.st_ino):
            raise WriterCutoverDenied("protected custody directory replaced")
    finally:
        os.close(other)



_WITNESS_LIMIT = 4096
_DIRECTORY_LIMIT = 65536
_WITNESS_SCHEMA = "skeleton.local-deployment-witness.v1"
_WITNESS_FIELDS = {"schema","deployment_sha256","authority_key_sha256",
                   "generation","latch_sha256","source_head",
                   "predecessor_generation","predecessor_latch_sha256",
                   "previous_local_sha256"}


def _hex(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}",value) is not None and value!="0"*64


def _witness_bytes(row):
    return json.dumps(row,sort_keys=True,separators=(",",":"),ensure_ascii=True,
                      allow_nan=False).encode("ascii")+b"\n"


def _witness_digest(row):
    return hashlib.sha256(b"skeleton.local-deployment-witness.v1\0"+_witness_bytes(row)).hexdigest()


def _witness_row(raw, deployment_key):
    def unique(pairs):
        row={}
        for key,value in pairs:
            if key in row:
                raise WriterCutoverDenied("duplicate local witness field")
            row[key]=value
        return row
    try:
        row=json.loads(raw.decode("ascii"),object_pairs_hook=unique)
        if (type(row) is not dict or set(row)!=_WITNESS_FIELDS
                or raw!=_witness_bytes(row)
                or row["schema"]!=_WITNESS_SCHEMA or row["deployment_sha256"]!=deployment_key
                or not _hex(row["authority_key_sha256"]) or not _hex(row["latch_sha256"])
                or type(row["source_head"]) is not str
                or re.fullmatch(r"[0-9a-f]{40}",row["source_head"]) is None
                or type(row["generation"]) is not int
                or not 1<=row["generation"]<(1<<63)
                or row["generation"]%2!=1
                or type(row["predecessor_generation"]) is not int
                or row["predecessor_generation"]!=row["generation"]-1
                or (row["generation"]==1 and row["predecessor_latch_sha256"] is not None)
                or (row["generation"]>1 and not _hex(row["predecessor_latch_sha256"]))
                or (row["previous_local_sha256"] is not None and not _hex(row["previous_local_sha256"]))):
            raise WriterCutoverDenied("malformed local deployment witness")
        return row
    except WriterCutoverDenied:
        raise
    except Exception:
        raise WriterCutoverDenied("malformed local deployment witness") from None


def _local_read(fd,name):
    handle=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=fd)
    try:
        _named_private_file(handle,name,fd)
        info=os.fstat(handle)
        def stamp(item):
            return item.st_dev,item.st_ino,item.st_size,item.st_mtime_ns,item.st_ctime_ns
        if not 1<=info.st_size<=4096:
            raise WriterCutoverDenied("local deployment witness size invalid")
        result=bytearray()
        while len(result)<info.st_size:
            block=os.read(handle,info.st_size-len(result))
            if not block:
                raise WriterCutoverDenied("local deployment witness truncated")
            result.extend(block)
        if os.read(handle,1) or stamp(info)!=stamp(os.fstat(handle)):
            raise WriterCutoverDenied("local deployment witness changed")
        _named_private_file(handle,name,fd)
        return bytes(result)
    finally:
        os.close(handle)


class _LocalDeploymentWitness:
    """Append-only, separate filesystem high-water witness.

    The enclosing launcher owns the directory descriptor and exclusive
    deployment lock. No automatic trimming, repair or filesystem rollback
    claim. A partial or malformed record requires explicit reconciliation.
    """
    def __init__(self,approval,directory,fd,lock,lock_name,deployment_key):
        self.approval,self.directory,self.fd,self.lock=approval,directory,fd,lock
        self.lock_name,self.deployment_key=lock_name,deployment_key
        self.prefix="witness-"+deployment_key+"-"
        self.closed=False
        self.recorded=False
        self.baseline=self._scan()
        self._check_predecessor(self.baseline)

    def _verify_directory(self):
        if self.closed:
            raise WriterCutoverDenied("local deployment witness closed")
        _same_directory(self.directory,self.fd)
        _named_private_file(self.lock,self.lock_name,self.fd)

    def _scan(self):
        self._verify_directory()
        rows=[]
        count=0
        # Do not load an unbounded directory list or follow symlink records.
        with os.scandir(self.fd) as entries:
            for entry in entries:
                count+=1
                if count>_DIRECTORY_LIMIT:
                    raise WriterCutoverDenied("local deployment custody directory limit exceeded")
                name=entry.name
                if not name.startswith(self.prefix):
                    continue
                suffix=name[len(self.prefix):]
                if re.fullmatch(r"[0-9]{19}\.json",suffix) is None or len(rows)>=_WITNESS_LIMIT:
                    raise WriterCutoverDenied("invalid or excessive local deployment witness records")
                row=_witness_row(_local_read(self.fd,name),self.deployment_key)
                if int(suffix[:-5])!=row["generation"]:
                    raise WriterCutoverDenied("local deployment witness name mismatch")
                rows.append(row)
        rows.sort(key=lambda row:row["generation"])
        previous=None
        key=hashlib.sha256(self.approval.public_key).hexdigest()
        for row in rows:
            if (row["authority_key_sha256"]!=key
                    or row["previous_local_sha256"]!=(None if previous is None else _witness_digest(previous))
                    or (previous is not None and row["generation"]<=previous["generation"])):
                raise WriterCutoverDenied("local deployment witness chain or authority changed")
            previous=row
        self._verify_directory()
        return previous

    def _check_predecessor(self,previous):
        self.approval.verify()
        if previous is not None and self.approval.plan.predecessor_generation<=previous["generation"]:
            raise WriterCutoverDenied("startup predecessor older than local deployment high-water")

    def record(self,reservation):
        """Persist actual shared reservation before enabling backend writers."""
        if self.closed or self.recorded:
            raise WriterCutoverDenied("local deployment witness already finalized")
        plan=self.approval.plan
        if (type(reservation) is not dict or set(reservation)!={"generation","latch_sha256"}
                or type(reservation["generation"]) is not int
                or reservation["generation"]!=plan.predecessor_generation+1
                or not _hex(reservation["latch_sha256"])):
            raise WriterCutoverDenied("local witness shared reservation mismatch")
        previous=self._scan()
        if previous!=self.baseline:
            raise WriterCutoverDenied("local deployment witness changed after preflight")
        self._check_predecessor(previous)
        row={"schema":_WITNESS_SCHEMA,"deployment_sha256":self.deployment_key,
             "authority_key_sha256":hashlib.sha256(self.approval.public_key).hexdigest(),
             "generation":reservation["generation"],"latch_sha256":reservation["latch_sha256"],
             "source_head":plan.source_head,"predecessor_generation":plan.predecessor_generation,
             "predecessor_latch_sha256":plan.predecessor_latch_sha256,
             "previous_local_sha256":None if previous is None else _witness_digest(previous)}
        raw=_witness_bytes(row)
        _witness_row(raw,self.deployment_key)
        name=self.prefix+f'{row["generation"]:019d}'+".json"
        handle=None
        try:
            self._verify_directory()
            handle=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|
                           os.O_CLOEXEC|os.O_NONBLOCK,0o600,dir_fd=self.fd)
            _named_private_file(handle,name,self.fd)
            view=memoryview(raw)
            while view:
                length=os.write(handle,view)
                if length<=0:
                    raise WriterCutoverDenied("local witness publication incomplete")
                view=view[length:]
            os.fsync(handle)
            os.fsync(self.fd)
            _named_private_file(handle,name,self.fd)
            self._verify_directory()
            if self._scan()!=row:
                raise WriterCutoverDenied("local witness publication not retained")
            self.approval.verify()
            self.recorded=True
            return {"generation":row["generation"],"witness_sha256":_witness_digest(row)}
        except OSError:
            raise WriterCutoverDenied("local deployment witness publication uncertain") from None
        finally:
            if handle is not None:
                os.close(handle)


@contextmanager
def _reserve_cutover(approval, directory):
    """Hold one local deployment lease and irrevocably reserve this approval.

    An interrupted/failed launch burns the approval. The on-disk marker is
    never removed or overwritten here. This guards one trusted filesystem,
    not multiple hosts, storage snapshot rollback or external Mongo writers.
    """
    if type(approval) is not VerifiedWriterCutover:
        raise WriterCutoverDenied("verified cutover approval required")
    approval.verify()
    import fcntl
    fd = lock = receipt = witness = None
    try:
        fd = _private_state_directory(directory)
        plan = approval.plan
        deployment_key = hashlib.sha256(
            b"skeleton.local-cutover-deployment.v1\0" + plan.deployment_id.encode("ascii")
        ).hexdigest()
        approval_key = hashlib.sha256(
            b"skeleton.local-cutover-reservation.v1\0" + plan.canonical_bytes()
        ).hexdigest()
        lock_name = "deployment-" + deployment_key + ".lock"
        receipt_name = "approval-" + approval_key + ".reserved"
        common = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        lock = os.open(lock_name, os.O_RDWR | os.O_CREAT | common, 0o600, dir_fd=fd)
        _named_private_file(lock, lock_name, fd)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise WriterCutoverDenied("local protected deployment already active") from None
        _named_private_file(lock, lock_name, fd)
        _same_directory(directory, fd)
        approval.verify()
        witness = _LocalDeploymentWitness(approval,directory,fd,lock,lock_name,deployment_key)
        # O_EXCL denies any pre-existing record, even an incomplete record
        # left by a killed process. Never infer success from marker contents.
        receipt = os.open(receipt_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | common,
                          0o600, dir_fd=fd)
        _named_private_file(receipt, receipt_name, fd)
        payload = json.dumps({
            "schema": "skeleton.local-cutover-reservation.v1",
            "approval_sha256": approval_key,
            "source_head": plan.source_head,
            "state": "reserved_not_qualified",
        }, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
        written = 0
        while written < len(payload):
            count = os.write(receipt, payload[written:])
            if count <= 0:
                raise WriterCutoverDenied("protected approval reservation incomplete")
            written += count
        os.fsync(receipt)
        os.fsync(fd)
        _named_private_file(receipt, receipt_name, fd)
        _same_directory(directory, fd)
        os.close(receipt)
        receipt = None
        approval.verify()
        # Verify state before handing control to the actual backend. The
        # operating system releases the advisory lock when this process dies.
        yield witness
    except WriterCutoverDenied:
        raise
    except OSError:
        raise WriterCutoverDenied("local protected approval custody unavailable or already consumed") from None
    finally:
        if witness is not None:
            witness.closed = True
        if receipt is not None:
            os.close(receipt)
        if lock is not None:
            os.close(lock)
        if fd is not None:
            os.close(fd)


def _source(expected):
    if re.fullmatch(r"[0-9a-f]{40}", expected or "") is None:
        raise WriterCutoverDenied("independent source pin required")
    command = ["git","-C",str(ROOT)]
    def run(*args):
        return subprocess.run(command+list(args), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              check=True, timeout=45).stdout
    if (run("rev-parse","HEAD").decode("ascii").strip() != expected
            or run("status","--porcelain","--untracked-files=no")):
        raise WriterCutoverDenied("reviewed checkout identity changed")
    # This only checks Git's tracked source view, not native binaries,
    # ignored files, import closure, storage provenance or package signer.


def _approval(args):
    _source(args.source_head)
    if re.fullmatch(r"[0-9a-f]{64}", args.operator_public_key_hex or "") is None:
        raise WriterCutoverDenied("independent Ed25519 public key pin required")
    if not args.plan or not args.signature or not args.authority or not args.deployment:
        raise WriterCutoverDenied("signed cutover plan and independent pins required")
    plan = CanonicalWriterCutover.parse(_file(args.plan, 256*1024))
    return VerifiedWriterCutover(plan, _file(args.signature,64), args.authority,
                                 args.deployment, args.source_head, bytes.fromhex(args.operator_public_key_hex))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect-only", action="store_true")
    mode.add_argument("--start-protected-backend", action="store_true")
    mode.add_argument("--inspect-deployment", action="store_true")
    mode.add_argument("--retire-deployment", action="store_true")
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--authority")
    parser.add_argument("--deployment")
    parser.add_argument("--operator-public-key-hex")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args(argv)
    try:
        _source(args.source_head)
        if args.inspect_deployment or args.retire_deployment:
            from core.databases import core_db
            from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch
            epoch = MongoCanonicalSourceEpoch(core_db)
            if args.inspect_deployment:
                if any(v is not None for v in (args.plan,args.signature,args.authority,args.deployment,args.operator_public_key_hex,args.state_dir)):
                    raise WriterCutoverDenied("observation cannot consume retirement approval")
                result = asyncio.run(inspect_writer_deployment(epoch=epoch))
            else:
                if (not args.plan or not args.signature or not args.authority or not args.deployment
                        or args.state_dir is not None
                        or re.fullmatch(r"[0-9a-f]{64}",args.operator_public_key_hex or "") is None):
                    raise WriterCutoverDenied("independently signed offline retirement required")
                plan = WriterDeploymentRetirement.parse(_file(args.plan,16384))
                result = asyncio.run(retire_writer_deployment(
                    plan,_file(args.signature,64),epoch=epoch,authority_id=args.authority,
                    deployment_id=args.deployment,source_head=args.source_head,
                    public_key=bytes.fromhex(args.operator_public_key_hex)))
            _source(args.source_head)
            result["source_head"] = args.source_head
            print(json.dumps(result,sort_keys=True))
            return 0
        if args.inspect_only:
            if any(v is not None for v in (args.plan,args.signature,args.authority,args.deployment,args.operator_public_key_hex,args.state_dir)):
                raise WriterCutoverDenied("inspection cannot consume approval")
            from core.canonical_writer_startup import inspect_configured_inventory
            receipt = asyncio.run(inspect_configured_inventory())
            _source(args.source_head)
            receipt["source_head"] = args.source_head
            print(json.dumps(receipt, sort_keys=True))
            return 0
        if not 1024 <= args.port <= 65535:
            raise WriterCutoverDenied("explicit unprivileged port required")
        approval = _approval(args)
        if args.state_dir is None:
            raise WriterCutoverDenied("independent protected local custody directory required")
        with _reserve_cutover(approval, args.state_dir) as witness:
            import uvicorn
            from backend.server import app
            from core.canonical_writer_startup import configure_cutover
            configure_cutover(app, approval, local_checkpoint=witness.record)
            _source(args.source_head)
            # One actual backend process, no auto-reload or remote bind. The
            # existing lifespan performs the live inventory check again.
            uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1, reload=False, log_level="warning")
            if getattr(app.state,"_writer_cutover_installed",False) is not True:
                raise WriterCutoverDenied("protected backend did not reach writer binding")
        return 0
    except Exception:
        print("Protected backend startup/inspection denied; no readiness grant.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
