"""Offline authored-choice QA, proof preview and playable handoff."""
from __future__ import annotations

import argparse
import json
import sys

from .playtest import PlaytestStore
from .world_canon import CanonError


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-playtest")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("preview", "compile", "verify"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "compile":
            cmd.add_argument("--expected-world-digest", required=True)
            cmd.add_argument("--allow-uncovered", action="store_true")
    args = parser.parse_args(argv)
    try:
        store = PlaytestStore(args.store)
        if args.action == "preview":
            result = {"ok": True, "coverage": store.preview(args.world_id)}
        elif args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, expected_world_digest=args.expected_world_digest,
                require_full_coverage=not args.allow_uncovered)}
        else:
            result = {"ok": True, "receipt": store.verify(args.world_id)}
    except (CanonError, OSError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
