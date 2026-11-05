"""Installed CLI for operator-keyed offline encrypted byte spill."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Sequence

from skeleton.app.offline_encrypted_spill import (
    EncryptedSpillStore, SpillError, SpillIdentity, SpillPolicy,
    NOFOLLOW, NONBLOCK, _read, _safe, _new, _directory_fd, _read_fd,
)


def _key(path: str) -> bytes:
    selected = Path(path)
    _safe(selected)
    with _directory_fd(selected.parent) as parent:
        fd = os.open(
            selected.name if parent is not None else selected,
            os.O_RDONLY | NOFOLLOW | NONBLOCK,
            **({"dir_fd": parent} if parent is not None else {}),
        )
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise SpillError("key must be a regular file")
            if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
                raise SpillError("key must be user-owned and mode 0600")
            key = _read_fd(fd, 32)
            if len(key) != 32:
                raise SpillError("key file must contain exactly 32 bytes")
            return key
        finally:
            os.close(fd)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skeleton-offline-spill")
    parser.add_argument("--store", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--max-entry-bytes", type=int, default=32 * 1024 * 1024)
    parser.add_argument("--max-total-bytes", type=int, default=2 * 1024 * 1024 * 1024)
    parser.add_argument("--min-free-bytes", type=int, default=256 * 1024 * 1024)
    commands = parser.add_subparsers(dest="command", required=True)
    put = commands.add_parser("put")
    put.add_argument("--input", required=True)
    get = commands.add_parser("get")
    get.add_argument("--id", required=True)
    get.add_argument("--output", required=True)
    delete = commands.add_parser("delete")
    delete.add_argument("--id", required=True)
    commands.add_parser("list")
    commands.add_parser("verify")
    commands.add_parser("prune")
    for sub in (put, get, delete):
        sub.add_argument("--model-sha256", required=True)
        sub.add_argument("--tokenizer-sha256", required=True)
        sub.add_argument("--context-id", required=True)
        sub.add_argument("--chunk-index", type=int, required=True)
    return parser


def _identity(args: argparse.Namespace) -> SpillIdentity:
    return SpillIdentity(args.model_sha256, args.tokenizer_sha256,
                         args.context_id, args.chunk_index)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        policy = SpillPolicy(args.max_entry_bytes, args.max_total_bytes, args.min_free_bytes)
        store = EncryptedSpillStore(args.store, _key(args.key_file), policy=policy)
        if args.command == "put":
            result = store.put(_read(Path(args.input), policy.max_entry_bytes), _identity(args))
        elif args.command == "get":
            payload = store.read(args.id, _identity(args))
            target = Path(args.output)
            _safe(target.parent, directory=True)
            if target.exists() or target.is_symlink():
                raise SpillError("output must not exist")
            _new(target, payload)
            result = {"record_id": args.id, "restored_bytes": len(payload)}
        elif args.command == "delete":
            store.delete(args.id, _identity(args))
            result = {"record_id": args.id, "deleted": True}
        elif args.command == "list":
            result = {"records": store.records()}
        elif args.command == "verify":
            result = store.verify()
        else:
            result = store.prune_orphans()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (SpillError, OSError, ValueError) as exc:
        print("offline spill rejected: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
