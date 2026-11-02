"""Reviewed lore authoring, branch proof and real player reveal CLI."""
from __future__ import annotations

import argparse
import json
import sys

from .lore import (
    LoreStore, approve_lore, edit_lore, propose_lore, reveal_lore,
)
from .lore_editor import LoreEditorStore
from .session import SessionStore
from .world_canon import CanonError, WorldStore, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-lore")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    proposal = sub.add_parser("propose")
    proposal.add_argument("--world-id", required=True)
    proposal.add_argument("--prompt", required=True)
    proposal.add_argument("--subject", required=True)
    proposal.add_argument("--statement", required=True)
    for action in ("inspect", "edit", "approve", "compile", "verify", "reveal",
                   "editor", "verify-editor"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action in ("edit", "approve", "compile", "editor"):
            cmd.add_argument("--expected-digest", required=True)
        if action == "edit":
            cmd.add_argument("--operation-json", required=True)
        if action == "approve":
            cmd.add_argument("--note", required=True)
        if action == "reveal":
            cmd.add_argument("--slot", required=True)
    args = parser.parse_args(argv)
    try:
        store = LoreStore(args.store)
        if args.action == "verify-editor":
            result = {"ok": True, "editor": LoreEditorStore(args.store).verify(
                args.world_id)}
        elif args.action == "editor":
            result = {"ok": True, "editor": LoreEditorStore(args.store).render(
                args.world_id, args.expected_digest)}
        elif args.action == "verify":
            result = {"ok": True, "receipt": store.verify(args.world_id)}
        elif args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, args.expected_digest)}
        else:
            world = WorldStore(args.store).read(args.world_id)
            if args.action == "propose":
                data = propose_lore(world, prompt=args.prompt,
                                    subject=args.subject, statement=args.statement)
                result = {"ok": True, "lore_digest": store.publish(
                    args.world_id, data, create=True), "review_required": True}
            else:
                data = store.read(args.world_id)
                if args.action == "inspect":
                    result = {"ok": True, "lore_digest": digest(data), "lore": data}
                elif args.action == "reveal":
                    if not data["approved"]:
                        raise CanonError("lore_review_required")
                    session = SessionStore(args.store).read(args.world_id, args.slot)
                    result = {"ok": True, "reveal": reveal_lore(data, world, session)}
                else:
                    if digest(data) != args.expected_digest:
                        raise CanonError("stale_lore")
                    if args.action == "edit":
                        updated = edit_lore(
                            data, world, strict_json(args.operation_json.encode("utf-8")))
                    else:
                        updated = approve_lore(data, world, args.note)
                    result = {"ok": True, "lore_digest": store.publish(
                        args.world_id, updated, expected_digest=args.expected_digest),
                        "review_required": not updated["approved"]}
    except (CanonError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
