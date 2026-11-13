"""Operator CLI for reviewed original character transformation arcs."""
from __future__ import annotations

import argparse
import json
import sys

from .character_arcs import ArcStore
from .world_canon import CanonError, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-character-arcs")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "inspect", "save", "edit", "approve",
                   "editor", "compile", "verify", "player"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "propose":
            for key in ("prompt", "actor", "desire", "starting-belief",
                        "resolved-belief", "choice", "text"):
                cmd.add_argument("--" + key, required=True)
        if action in ("save", "edit", "approve", "editor", "compile"):
            cmd.add_argument("--expected-digest")
        if action == "save":
            cmd.add_argument("--source-json", required=True)
            cmd.add_argument("--create", action="store_true")
        if action == "edit":
            cmd.add_argument("--operation-json", required=True)
        if action == "approve":
            cmd.add_argument("--review-note", required=True)
        if action == "player":
            cmd.add_argument("--slot", required=True)
    args = parser.parse_args(argv)
    try:
        store = ArcStore(args.store)
        if args.action == "propose":
            result = {"proposal": store.propose(
                args.world_id, prompt=args.prompt, actor=args.actor,
                desire=args.desire, starting_belief=args.starting_belief,
                resolved_belief=args.resolved_belief,
                choice=args.choice, text=args.text), "review_required": True}
        elif args.action == "inspect":
            result = store.inspect(args.world_id)
        elif args.action == "save":
            result = {"arcs_digest": store.publish(
                args.world_id, strict_json(args.source_json.encode("utf-8")),
                expected_digest=args.expected_digest, create=args.create)}
        elif args.action == "edit":
            result = {"arcs_digest": store.edit(
                args.world_id, args.expected_digest,
                strict_json(args.operation_json.encode("utf-8")))}
        elif args.action == "approve":
            result = {"arcs_digest": store.approve(
                args.world_id, args.expected_digest, args.review_note)}
        elif args.action == "editor":
            result = store.editor(args.world_id, args.expected_digest)
        elif args.action == "compile":
            result = {"receipt": store.compile(args.world_id, args.expected_digest)}
        elif args.action == "player":
            result = store.player(args.world_id, args.slot)
        else:
            result = {"receipt": store.verify(args.world_id)}
    except (CanonError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "invalid_input"},
                         sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
