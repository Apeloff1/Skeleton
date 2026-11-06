"""Operator-authorized CLI for original world proposal, edit, proof and play."""
from __future__ import annotations

import argparse
import json
import errno
import os
import stat
import sys

from .world_canon import CanonError, WorldStore, digest, edit, propose, prove, strict_json


def _read_operation_file(path: str) -> bytes:
    """Bounded descriptor-relative review read; reject symlinks in every component."""
    if not all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")):
        raise CanonError("operation_secure_open_unavailable")
    if not isinstance(path, str) or not path or "\x00" in path:
        raise CanonError("operation_invalid_path")
    absolute = os.path.isabs(path)
    parts = path.split(os.sep)
    if absolute:
        parts = parts[1:]
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise CanonError("operation_invalid_path")
    directory_flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                       os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
    directory = os.open(os.sep if absolute else ".", directory_flags)
    try:
        for part in parts[:-1]:
            child = os.open(part, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        flags = (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                 getattr(os, "O_CLOEXEC", 0))
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
            after = os.fstat(fd)
            if (after.st_dev != info.st_dev or after.st_ino != info.st_ino
                    or after.st_size != info.st_size
                    or after.st_mtime_ns != info.st_mtime_ns
                    or after.st_ctime_ns != info.st_ctime_ns
                    or len(raw) != info.st_size):
                raise CanonError("operation_changed_during_read")
            if not raw:
                raise CanonError("operation_empty")
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
        # Validate operator input before constructing or touching the canonical
        # custody store. A rejected operation must have no filesystem effects.
        operation = (strict_json(_read_operation_file(args.operation_file))
                     if args.action == "edit" else None)
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
        error = exc.code if isinstance(exc, CanonError) else {
            errno.ELOOP: "operation_symlink_disallowed",
            errno.ENOENT: "operation_missing",
            errno.EACCES: "operation_permission_denied",
            errno.EPERM: "operation_permission_denied",
            errno.ENOTDIR: "operation_invalid_directory",
        }.get(exc.errno, "io_error")
        result = {"ok": False, "error": error}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
