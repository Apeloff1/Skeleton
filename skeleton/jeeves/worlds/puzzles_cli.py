"""Reviewed original scene puzzle authoring and compile CLI."""
from __future__ import annotations

import argparse
import json
import sys

from .puzzles import PuzzleStore, edit_puzzles
from .world_canon import CanonError, WorldStore, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-puzzles")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "inspect", "save", "edit", "editor", "approve", "compile", "verify"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "propose":
            for field in ("prompt", "puzzle-id", "scene", "question", "answer",
                          "hint", "unlock-choice"):
                cmd.add_argument("--" + field, required=True)
        if action in ("save", "edit", "editor", "approve", "compile"):
            cmd.add_argument("--expected-digest")
        if action == "save":
            cmd.add_argument("--puzzles-json", required=True)
            cmd.add_argument("--create", action="store_true")
        if action == "edit":
            cmd.add_argument("--operation-json", required=True)
        if action == "approve":
            cmd.add_argument("--review-note", required=True)
    args = parser.parse_args(argv)
    try:
        store = PuzzleStore(args.store)
        if args.action == "propose":
            result = {"proposal": store.propose(
                args.world_id, prompt=args.prompt, puzzle_id=args.puzzle_id,
                scene=args.scene, question=args.question, answer=args.answer,
                hint=args.hint, unlock_choice=args.unlock_choice,
            ), "review_required": True}
        elif args.action == "inspect":
            result = store.inspect(args.world_id)
        elif args.action == "save":
            result = {"puzzles_digest": store.publish(
                args.world_id, strict_json(args.puzzles_json.encode("utf-8")),
                expected_digest=args.expected_digest, create=args.create,
            ), "review_required": True}
        elif args.action == "edit":
            current = store.inspect(args.world_id)["puzzles"]
            if digest(current) != args.expected_digest:
                raise CanonError("puzzles_stale_edit")
            world = WorldStore(args.store).read(args.world_id)
            updated = edit_puzzles(
                current, world, strict_json(args.operation_json.encode("utf-8")),
            )
            result = {"puzzles_digest": store.publish(
                args.world_id, updated, expected_digest=args.expected_digest,
            ), "review_required": True}
        elif args.action == "editor":
            result = {"editor": store.editor(args.world_id, args.expected_digest)}
        elif args.action == "approve":
            result = {"puzzles_digest": store.approve(
                args.world_id, expected_digest=args.expected_digest,
                review_note=args.review_note,
            ), "review_required": False}
        elif args.action == "compile":
            result = {"receipt": store.compile(args.world_id, args.expected_digest)}
        else:
            result = {"receipt": store.verify(args.world_id)}
    except (CanonError, OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({
            "ok": False,
            "error": exc.code if isinstance(exc, CanonError) else "io_error",
        }, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
