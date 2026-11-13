"""Source-verified offline CLI play and portable checkpoint recovery."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys

from .session import SessionStore
from .world_canon import CanonError, strict_json


def _bounded_import(path: str):
    if not hasattr(os, "O_NOFOLLOW"):
        raise CanonError("platform_not_supported")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 524288:
            raise CanonError("unsafe_import_file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            return strict_json(stream.read(524289))
    finally:
        os.close(fd)


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-session")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("new", "inspect", "choose", "export", "import"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        cmd.add_argument("--slot", required=True)
        if action == "choose":
            cmd.add_argument("--choice-id", required=True)
            cmd.add_argument("--expected-digest", required=True)
        if action == "import":
            cmd.add_argument("--checkpoint-file", required=True)
    args = parser.parse_args(argv)
    try:
        store = SessionStore(args.store)
        if args.action == "new":
            result = {"ok": True, "player": store.create(args.world_id, args.slot)}
        elif args.action == "inspect":
            result = {"ok": True, "player": store.inspect(args.world_id, args.slot)}
        elif args.action == "choose":
            result = {"ok": True, "player": store.choose(
                args.world_id, args.slot, args.choice_id, args.expected_digest)}
        elif args.action == "export":
            result = {"ok": True, "checkpoint": store.export(
                args.world_id, args.slot)}
        else:
            checkpoint = _bounded_import(args.checkpoint_file)
            result = {"ok": True, "player": store.create(
                args.world_id, args.slot, imported=checkpoint)}
    except (CanonError, OSError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
