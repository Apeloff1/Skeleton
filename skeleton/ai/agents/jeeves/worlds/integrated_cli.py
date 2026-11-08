"""Operator CLI for unified original-world experience and continuity proof."""
from __future__ import annotations

import argparse
import json
import sys

from .integrated_experience import IntegratedExperienceStore
from .world_canon import CanonError


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-integrated")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("compile", "verify", "player"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "compile":
            for name in ("world-digest", "cast-digest", "route-digest",
                         "promises-digest", "context-head"):
                cmd.add_argument("--" + name, required=True)
        if action == "player":
            cmd.add_argument("--slot", required=True)
    args = parser.parse_args(argv)
    try:
        store = IntegratedExperienceStore(args.store)
        if args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, world_digest=args.world_digest,
                cast_digest=args.cast_digest, route_digest=args.route_digest,
                promises_digest=args.promises_digest, context_head=args.context_head)}
        elif args.action == "verify":
            result = {"ok": True, "receipt": store.verify(args.world_id)}
        else:
            result = {"ok": True, "player": store.player(args.world_id, args.slot)}
    except (CanonError, OSError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
