"""Read-only studio assembly previews and exact-lease offline compilation."""
from __future__ import annotations

import argparse
import json
import sys

from .studio_assembly import StudioAssemblyStore
from .world_canon import CanonError, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-studio")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("inspect", "compile", "verify", "player", "preview"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "compile":
            cmd.add_argument("--expected-digests-json", required=True)
        if action in ("player", "preview"):
            cmd.add_argument("--locale", required=True)
        if action == "player":
            cmd.add_argument("--slot", required=True)
        if action == "preview":
            cmd.add_argument("--choices-json", required=True)
    args = parser.parse_args(argv)
    try:
        store = StudioAssemblyStore(args.store)
        if args.action == "inspect":
            result = store.inspect(args.world_id)
        elif args.action == "compile":
            result = {"receipt": store.compile(
                args.world_id, strict_json(args.expected_digests_json.encode("utf-8")))}
        elif args.action == "verify":
            result = {"receipt": store.verify(args.world_id)}
        elif args.action == "player":
            result = store.player(args.world_id, args.slot, args.locale)
        else:
            result = {"player": store.preview(
                args.world_id, strict_json(args.choices_json.encode("utf-8")),
                args.locale)}
    except (CanonError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "invalid_input"}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
