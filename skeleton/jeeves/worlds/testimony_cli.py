"""Operator-only reviewed testimony CLI; model tools cannot approve or publish."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .testimony import TestimonyStore, edit_testimony, replay_testimony
from .world_canon import CanonError, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-testimony")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "inspect", "save", "edit", "approve",
                   "editor", "compile", "verify", "player", "player-slot"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "propose":
            for field in ("prompt", "statement-id", "actor", "scene", "choice",
                          "claim", "stance", "text", "provenance"):
                cmd.add_argument("--" + field, required=True)
        if action in ("save", "edit", "approve", "editor", "compile"):
            cmd.add_argument("--expected-digest")
        if action == "save":
            cmd.add_argument("--testimony-json", required=True)
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
        store = TestimonyStore(args.store)
        if args.action == "propose":
            result = {"proposal": store.propose(
                args.world_id, prompt=args.prompt, statement_id=args.statement_id,
                actor=args.actor, scene=args.scene, choice=args.choice,
                claim=args.claim, stance=args.stance, text=args.text,
                provenance=args.provenance), "review_required": True}
        elif args.action == "inspect":
            result = store.inspect(args.world_id)
        elif args.action == "save":
            result = {"testimony_digest": store.publish(
                args.world_id, strict_json(args.testimony_json.encode("utf-8")),
                expected_digest=args.expected_digest, create=args.create),
                "review_required": True}
        elif args.action == "edit":
            current = store.inspect(args.world_id)["testimony"]
            if digest(current) != args.expected_digest:
                raise CanonError("testimony_stale_edit")
            fd = store.worlds._directory()
            try:
                world, cast = store._sources(fd, args.world_id)
                candidate = edit_testimony(
                    current, world, cast, strict_json(args.operation_json.encode("utf-8")))
            finally:
                os.close(fd)
            result = {"testimony_digest": store.publish(
                args.world_id, candidate, expected_digest=args.expected_digest),
                "review_required": True}
        elif args.action == "approve":
            result = {"testimony_digest": store.approve(
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
                world, cast = store._sources(fd, args.world_id)
                source = store._read(fd, args.world_id, world, cast)
                if not source["approved"] or not cast["approved"]:
                    raise CanonError("testimony_review_required")
                result = {"player": replay_testimony(
                    source, world, cast, strict_json(args.choices_json.encode("utf-8")))}
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
