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
    fd = lock = receipt = None
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
        yield
    except WriterCutoverDenied:
        raise
    except OSError:
        raise WriterCutoverDenied("local protected approval custody unavailable or already consumed") from None
    finally:
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
        with _reserve_cutover(approval, args.state_dir):
            import uvicorn
            from backend.server import app
            from core.canonical_writer_startup import configure_cutover
            configure_cutover(app, approval)
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
