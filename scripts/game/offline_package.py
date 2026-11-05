"""Offline source archive CLI: build and verify without extraction.

python -m scripts.game.offline_package pack --input package.json --out game.zip
python -m scripts.game.offline_package verify --archive game.zip
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import stat
import sys

from skeleton.game.build.flgb_build_runtime import BuildContractError
from skeleton.game.build.offline_package import MAX_ARCHIVE, build_package, verify_package

MAX_INPUT = 12_000_000


def _read(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise BuildContractError("input must be a bounded regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise BuildContractError("input byte budget exceeded")
        return data
    finally:
        os.close(fd)


def _write(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise OSError("short archive write")
            view = view[n:]
        os.fsync(fd)
    except BaseException:
        inode = os.fstat(fd).st_ino
        os.close(fd)
        try:
            if path.lstat().st_ino == inode:
                path.unlink()
        except OSError:
            pass
        raise
    else:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("pack", "verify"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "verify":
            if args.archive is None or args.input is not None or args.out is not None:
                raise BuildContractError("verify requires only --archive")
            print(json.dumps(verify_package(_read(args.archive, MAX_ARCHIVE)), sort_keys=True))
            return 0
        if args.input is None or args.out is None or args.archive is not None:
            raise BuildContractError("pack requires --input and --out")
        source = json.loads(_read(args.input, MAX_INPUT))
        if not isinstance(source, dict) or set(source) != {"package_id", "author", "license", "files"}:
            raise BuildContractError("invalid package input")
        members = source["files"]
        if not isinstance(members, list) or len(members) > 128:
            raise BuildContractError("invalid source file count")
        files = {}
        for item in members:
            if not isinstance(item, dict) or set(item) != {"path", "content_base64"}:
                raise BuildContractError("invalid source entry")
            if item["path"] in files:
                raise BuildContractError("duplicate source path")
            if not isinstance(item["content_base64"], str) or len(item["content_base64"]) > 1_400_000:
                raise BuildContractError("invalid base64 content")
            files[item["path"]] = base64.b64decode(item["content_base64"], validate=True)
        payload = build_package(source["package_id"], source["author"], source["license"], files)
        receipt = verify_package(payload)
        _write(args.out, payload)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (BuildContractError, OSError, ValueError, TypeError, binascii.Error,
            json.JSONDecodeError) as exc:
        print(f"offline-package: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
