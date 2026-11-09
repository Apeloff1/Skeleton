"""Original ending epilogues: typed preview, review, earned replay and compile."""
from __future__ import annotations

import argparse
import json
import sys

from .epilogues import EpilogueStore
from .session_cli import _bounded_import
from .world_canon import CanonError, _keys


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-epilogues")
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
    args = parser.parse_args(argv)
    try:
        store = EpilogueStore(args.store)
        if args.action == "propose":
            data = _keys(_bounded_import(args.file), {"prompt", "entries"})
            result = {"proposal": store.propose(args.world_id, **data),
                      "review_required": True}
        elif args.action == "publish":
            source = _bounded_import(args.file)
            result = {"source_digest": store.publish(
                args.world_id, source,
                expected_digest=None if args.create else args.expected_digest,
                create=args.create), "review_required": True}
        elif args.action == "approve":
            result = {"source_digest": store.approve(
                args.world_id, args.expected_digest, args.note)}
        elif args.action == "editor":
            result = store.editor(args.world_id, args.expected_digest)
        elif args.action == "inspect":
            result = store.inspect(args.world_id)
        elif args.action == "player":
            result = store.player(args.world_id, args.slot)
        elif args.action == "compile":
            result = store.compile(args.world_id, args.slot,
                                   args.expected_digest,
                                   args.expected_session_digest)
        else:
            result = store.verify(args.world_id, args.slot)
    except (CanonError, OSError, TypeError, ValueError) as exc:
        code = exc.code if isinstance(exc, CanonError) else "epilogues_invalid_input"
        print(json.dumps({"ok": False, "error": code}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "result": result}, sort_keys=True,
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
