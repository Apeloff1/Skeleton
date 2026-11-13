"""Operator-reviewed scene advisory authoring and source-leased compilation."""
from __future__ import annotations

import argparse
import json
import sys

from .advisories import AdvisoryStore
from .session_cli import _bounded_import
from .world_canon import CanonError, _keys


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-advisories")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "publish", "inspect", "approve",
                   "player", "compile", "verify", "editor"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action in {"propose", "publish"}:
            cmd.add_argument("--file", required=True)
        if action == "publish":
            cmd.add_argument("--create", action="store_true")
        if action in {"publish", "approve", "compile", "editor"}:
            cmd.add_argument("--expected-digest", required=True)
        if action == "approve":
            cmd.add_argument("--note", required=True)
        if action in {"player", "compile", "verify"}:
            cmd.add_argument("--slot", required=True)
        if action == "compile":
            cmd.add_argument("--expected-session-digest", required=True)
        if action in {"player", "compile"}:
            cmd.add_argument("--accept", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        store = AdvisoryStore(args.store)
        if args.action == "propose":
            data = _keys(_bounded_import(args.file), {"prompt", "entries"})
            result = {"proposal": store.propose(args.world_id, **data),
                      "review_required": True}
        elif args.action == "publish":
            result = {"source_digest": store.publish(
                args.world_id, _bounded_import(args.file),
                create=args.create,
                expected_digest=None if args.create else args.expected_digest),
                "review_required": True}
        elif args.action == "inspect":
            result = store.inspect(args.world_id)
        elif args.action == "approve":
            result = {"source_digest": store.approve(
                args.world_id, args.expected_digest, args.note)}
        elif args.action == "player":
            result = store.player(args.world_id, args.slot, sorted(args.accept))
        elif args.action == "compile":
            result = store.compile(
                args.world_id, args.slot, args.expected_digest,
                args.expected_session_digest, sorted(args.accept))
        elif args.action == "verify":
            result = store.verify(args.world_id, args.slot)
        else:
            result = store.editor(args.world_id, args.expected_digest)
    except (CanonError, OSError, ValueError, TypeError) as exc:
        error = exc.code if isinstance(exc, CanonError) else "advisories_invalid_input"
        print(json.dumps({"ok": False, "error": error}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "result": result},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
