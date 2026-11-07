"""Operator CLI for bounded, source-leased narrative context replay."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys

from .context_journal import ContextStore
from .world_canon import CanonError, _keys, strict_json

REQUEST_SCHEMA = "jeeves.world.context_append_request.v1"


def _operation_file(path: str) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 524288:
            raise CanonError("unsafe_context_operation")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(524289)
        if len(raw) > 524288:
            raise CanonError("context_operation_too_large")
        return strict_json(raw)
    finally:
        os.close(fd)


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-context")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("create", "append", "status", "inspect", "compile",
                   "verify", "editor", "verify-editor"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "append":
            group = cmd.add_mutually_exclusive_group(required=True)
            group.add_argument("--operation-file")
            group.add_argument("--text")
            cmd.add_argument("--kind")
            cmd.add_argument("--expected-head")
        if action in ("compile", "editor"):
            cmd.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    try:
        store = ContextStore(args.store)
        if args.action == "create":
            result = {"ok": True, "status": store.create(args.world_id)}
        elif args.action == "status":
            result = {"ok": True, "status": store.status(args.world_id)}
        elif args.action == "inspect":
            result = {"ok": True, "journal": store.read(args.world_id)}
        elif args.action == "append":
            if args.operation_file is not None:
                request = _keys(_operation_file(args.operation_file), {
                    "schema", "world_id", "expected_head", "kind", "text",
                })
                if request["schema"] != REQUEST_SCHEMA or request["world_id"] != args.world_id:
                    raise CanonError("context_request_mismatch")
                head, kind, note = (
                    request["expected_head"], request["kind"], request["text"])
            else:
                if args.kind is None or args.expected_head is None:
                    raise CanonError("context_missing_lease_or_kind")
                head, kind, note = args.expected_head, args.kind, args.text
            result = {"ok": True, "status": store.append(
                args.world_id, expected_head=head, kind=kind, text=note)}
        elif args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, args.expected_head)}
        elif args.action == "verify":
            result = {"ok": True, "receipt": store.verify(args.world_id)}
        else:
            from .context_editor import ContextEditorStore
            editor = ContextEditorStore(args.store)
            receipt = (editor.render(args.world_id, args.expected_head)
                       if args.action == "editor" else editor.verify(args.world_id))
            result = {"ok": True, "editor": receipt}
    except (CanonError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
