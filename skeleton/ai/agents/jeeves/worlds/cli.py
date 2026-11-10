"""Operator-authorized CLI for original world proposal, edit, proof and play."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys

from .world_canon import CanonError, WorldStore, digest, edit, propose, prove, strict_json


def _read_operation_file(path: str) -> bytes:
    """Bounded descriptor-relative review read; reject symlinks in every component."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise CanonError("operation_secure_open_unavailable")
    if not path or "\\x00" in path:
        raise CanonError("operation_invalid_path")
    absolute = os.path.isabs(path)
    parts = path.split(os.sep)
    if absolute:
        parts = parts[1:]
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise CanonError("operation_invalid_path")
    directory = os.open(os.sep if absolute else ".", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(parts[-1], flags, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise CanonError("operation_not_regular")
            if info.st_size > 524288:
                raise CanonError("operation_too_large")
            with os.fdopen(os.dup(fd), "rb") as stream:
                raw = stream.read(524289)
            if len(raw) > 524288:
                raise CanonError("operation_too_large")
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(directory)

def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-canon")
    parser.add_argument("--store", required=True, help="private world custody directory")
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("propose")
    for field in ("id", "premise", "protagonist", "region", "goal"):
        plan.add_argument("--" + field, required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--id", required=True)
    patch = sub.add_parser("edit")
    patch.add_argument("--id", required=True)
    patch.add_argument("--expected-digest", required=True)
    patch.add_argument("--operation-file", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("--id", required=True)
    compile_cmd.add_argument("--expected-digest", required=True)
    args = parser.parse_args(argv)
    try:
        store = WorldStore(args.store)
        if args.action == "propose":
            source = propose(world_id=args.id, premise=args.premise,
                             protagonist=args.protagonist, region=args.region,
                             goal=args.goal)
            source_digest = store.publish(source, create=True)
            result = {"ok": True, "world_id": args.id,
                      "source_digest": source_digest,
                      "proof": prove(source).as_dict(),
                      "review_required": True}
        elif args.action == "inspect":
            source = store.read(args.id)
            result = {"ok": True, "world": source,
                      "proof": prove(source).as_dict()}
        elif args.action == "edit":
            # A user-authored JSON operation is a reviewable typed edit, never
            # arbitrary executable code or an implicit language-model action.
            operation = strict_json(_read_operation_file(args.operation_file))
            source = store.read(args.id)
            if digest(source) != args.expected_digest:
                raise CanonError("stale_source")
            updated = edit(source, operation)
            new_digest = store.publish(updated, expected_digest=args.expected_digest)
            result = {"ok": True, "world_id": args.id,
                      "source_digest": new_digest,
                      "proof": prove(updated).as_dict()}
        else:
            result = {"ok": True, **store.compile(args.id, args.expected_digest)}
    except (CanonError, OSError) as exc:
        result = {"ok": False, "error": exc.code if isinstance(exc, CanonError)
                  else "io_error"}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
