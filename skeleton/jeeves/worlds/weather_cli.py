"""Operator-reviewed weather source and deterministic replay CLI."""
from __future__ import annotations

import argparse
import json
import sys

from .weather import WeatherStore
from .session_cli import _bounded_import
from .world_canon import CanonError, _keys


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-weather")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "publish", "inspect", "approve",
                   "player", "compile", "verify", "editor",
                   "compile-playable", "verify-playable"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action in {"propose", "publish"}:
            cmd.add_argument("--file", required=True)
        if action == "publish":
            cmd.add_argument("--create", action="store_true")
        if action in {"publish", "approve", "compile", "editor", "compile-playable"}:
            cmd.add_argument("--expected-digest", required=True)
        if action == "approve":
            cmd.add_argument("--note", required=True)
        if action in {"player", "compile", "verify"}:
            cmd.add_argument("--slot", required=True)
        if action == "compile":
            cmd.add_argument("--expected-session-digest", required=True)
    args = parser.parse_args(argv)
    try:
        store = WeatherStore(args.store)
        if args.action == "propose":
            data = _keys(_bounded_import(args.file),
                         {"prompt", "scenes", "overrides"})
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
            result = store.player(args.world_id, args.slot)
        elif args.action == "compile":
            result = store.compile(args.world_id, args.slot, args.expected_digest,
                                   args.expected_session_digest)
        elif args.action == "verify":
            result = store.verify(args.world_id, args.slot)
        elif args.action == "compile-playable":
            result = store.compile_playable(args.world_id, args.expected_digest)
        elif args.action == "verify-playable":
            result = store.verify_playable(args.world_id)
        else:
            result = store.editor(args.world_id, args.expected_digest)
    except (CanonError, OSError, ValueError, TypeError) as exc:
        code = exc.code if isinstance(exc, CanonError) else "weather_invalid_input"
        print(json.dumps({"ok": False, "error": code}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "result": result}, sort_keys=True,
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
