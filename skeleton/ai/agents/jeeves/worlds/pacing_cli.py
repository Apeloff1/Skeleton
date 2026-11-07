"""Operator-reviewed narrative pacing CLI and verified HTML5 handoff."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .pacing import PacingStore, edit_pacing, replay_pacing
from .world_canon import CanonError, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-pacing")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "inspect", "save", "edit", "approve",
                   "editor", "compile", "verify", "player", "player-slot"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "propose":
            cmd.add_argument("--prompt", required=True)
            cmd.add_argument("--beats-json", required=True)
        if action in ("save", "edit", "approve", "editor", "compile"):
            cmd.add_argument("--expected-digest")
        if action == "save":
            cmd.add_argument("--pacing-json", required=True)
            cmd.add_argument("--create", action="store_true")
        if action == "edit":
            cmd.add_argument("--operation-json", required=True)
        if action == "approve":
            cmd.add_argument("--review-note", required=True)
        if action == "player":
            cmd.add_argument("--choices-json", required=True)
        if action == "player-slot":
            cmd.add_argument("--slot", required=True)
    args = parser.parse_args(argv)
    try:
        store = PacingStore(args.store)
        if args.action == "propose":
            result = {"proposal": store.propose(
                args.world_id, prompt=args.prompt,
                beats=strict_json(args.beats_json.encode("utf-8"))),
                "review_required": True}
        elif args.action == "inspect":
            result = store.inspect(args.world_id)
        elif args.action == "save":
            result = {"pacing_digest": store.publish(
                args.world_id, strict_json(args.pacing_json.encode("utf-8")),
                expected_digest=args.expected_digest, create=args.create),
                "review_required": True}
        elif args.action == "edit":
            current = store.inspect(args.world_id)["pacing"]
            if digest(current) != args.expected_digest:
                raise CanonError("pacing_stale_edit")
            fd = store.worlds._directory()
            try:
                world = store._world(fd, args.world_id)
                candidate = edit_pacing(
                    current, world, strict_json(args.operation_json.encode("utf-8")))
            finally:
                os.close(fd)
            result = {"pacing_digest": store.publish(
                args.world_id, candidate, expected_digest=args.expected_digest),
                "review_required": True}
        elif args.action == "approve":
            result = {"pacing_digest": store.approve(
                args.world_id, expected_digest=args.expected_digest,
                review_note=args.review_note), "review_required": False}
        elif args.action == "editor":
            result = {"editor": store.editor(args.world_id, args.expected_digest)}
        elif args.action == "compile":
            result = {"receipt": store.compile(args.world_id, args.expected_digest)}
        elif args.action == "verify":
            result = {"receipt": store.verify(args.world_id)}
        elif args.action == "player-slot":
            result = store.player(args.world_id, args.slot)
        else:
            fd = store.worlds._directory()
            try:
                world = store._world(fd, args.world_id)
                source = store._read(fd, args.world_id, world)
                if not source["approved"]:
                    raise CanonError("pacing_review_required")
                result = {"player": replay_pacing(
                    source, world, strict_json(args.choices_json.encode("utf-8")))}
            finally:
                os.close(fd)
    except (CanonError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "invalid_input"}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
