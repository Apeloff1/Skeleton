"""Operator CLI for original chapter/act source, proof, review and handoff."""
from __future__ import annotations

import argparse
import json
import sys

from .chapters import ChapterStore, edit_chapters
from .world_canon import CanonError, WorldStore, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-chapters")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "inspect", "publish", "edit", "approve",
                   "compile", "verify", "editor", "player"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--id", required=True)
        if action in {"propose", "publish", "edit"}:
            cmd.add_argument("--file", required=True)
        if action in {"publish", "edit", "approve", "compile", "editor"}:
            cmd.add_argument("--expected-digest")
        if action == "publish":
            cmd.add_argument("--create", action="store_true")
        if action == "approve":
            cmd.add_argument("--note", required=True)
        if action == "player":
            cmd.add_argument("--slot", required=True)
    args = parser.parse_args(argv)
    try:
        store = ChapterStore(args.store)
        if args.action in {"propose", "publish", "edit"}:
            with open(args.file, "rb") as stream:
                data = strict_json(stream.read(524289))
        if args.action == "propose":
            if type(data) is not dict or set(data) != {"prompt", "chapters"}:
                raise CanonError("chapters_invalid_proposal")
            result = {"proposal": store.propose(args.id, **data),
                      "review_required": True}
        elif args.action == "inspect":
            result = store.inspect(args.id)
        elif args.action == "publish":
            if not args.create and not args.expected_digest:
                raise CanonError("chapters_expected_digest_required")
            result = {"chapters_digest": store.publish(
                args.id, data, expected_digest=args.expected_digest,
                create=args.create), "review_required": True}
        elif args.action == "edit":
            if not args.expected_digest:
                raise CanonError("chapters_expected_digest_required")
            snapshot = store.inspect(args.id)
            if digest(snapshot["chapters"]) != args.expected_digest:
                raise CanonError("chapters_stale_edit")
            world = WorldStore(args.store).read(args.id)
            edited = edit_chapters(snapshot["chapters"], world, data)
            result = {"chapters_digest": store.publish(
                args.id, edited, expected_digest=args.expected_digest),
                "review_required": True}
        elif args.action == "approve":
            result = {"chapters_digest": store.approve(
                args.id, args.expected_digest or "", args.note)}
        elif args.action == "compile":
            result = store.compile(args.id, args.expected_digest or "")
        elif args.action == "verify":
            result = store.verify(args.id)
        elif args.action == "editor":
            result = store.editor(args.id, args.expected_digest or "")
        else:
            result = store.player(args.id, args.slot)
    except (CanonError, OSError, TypeError, ValueError) as exc:
        code = exc.code if isinstance(exc, CanonError) else "invalid_chapters_input"
        print(json.dumps({"ok": False, "error": code}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
