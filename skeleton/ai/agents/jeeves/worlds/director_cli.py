"""CLI for unified reviewed chapter/cinematic player and engine handoff."""
from __future__ import annotations

import argparse
import json
import sys

from .director import DirectorStore
from .world_canon import CanonError, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-director")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("inspect", "compile", "verify", "player"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--id", required=True)
        if action == "compile":
            cmd.add_argument("--expected-digests-json", required=True)
        if action == "player":
            cmd.add_argument("--slot", required=True)
    args = parser.parse_args(argv)
    try:
        store = DirectorStore(args.store)
        if args.action == "inspect":
            result = store.inspect(args.id)
        elif args.action == "compile":
            result = {"receipt": store.compile(
                args.id, strict_json(args.expected_digests_json.encode("utf-8")))}
        elif args.action == "verify":
            result = {"receipt": store.verify(args.id)}
        else:
            result = store.player(args.id, args.slot)
    except (CanonError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": (
            exc.code if isinstance(exc, CanonError) else "director_invalid_input")},
            sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
