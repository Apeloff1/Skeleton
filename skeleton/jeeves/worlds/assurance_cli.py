"""Operator CLI for unified scenario, invariant and choice-impact proof."""
from __future__ import annotations

import argparse
import json
import sys

from .assurance import AssuranceStore
from .world_canon import CanonError


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-assurance")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("preview", "compile", "verify"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "compile":
            cmd.add_argument("--expected-world-digest", required=True)
    args = parser.parse_args(argv)
    try:
        store = AssuranceStore(args.store)
        if args.action == "preview":
            result = {"ok": True, "preview": store.preview(args.world_id)}
        elif args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, expected_world_digest=args.expected_world_digest,
            )}
        else:
            result = {"ok": True, "receipt": store.verify(args.world_id)}
    except (CanonError, OSError) as exc:
        print(json.dumps({
            "ok": False,
            "error": exc.code if isinstance(exc, CanonError) else "io_error",
        }, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
