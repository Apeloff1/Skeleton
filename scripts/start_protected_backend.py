"""Independent operator launch for protected canonical backend writers.

Run from a reviewed, clean project checkout with PYTHONPATH=.:backend.
This executable never migrates, generates an approval, writes an epoch or
activates guarded AI. A normal application boot is not the protected mode.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/"backend")]
from skeleton.app.canonical_writer_cutover import CanonicalWriterCutover, VerifiedWriterCutover, WriterCutoverDenied


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
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--authority")
    parser.add_argument("--deployment")
    parser.add_argument("--operator-public-key-hex")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args(argv)
    try:
        _source(args.source_head)
        if args.inspect_only:
            if any(v is not None for v in (args.plan,args.signature,args.authority,args.deployment,args.operator_public_key_hex)):
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
