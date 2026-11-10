"""Original authored quest CLI with real player-session progress replay."""
from __future__ import annotations

import argparse
import json
import sys

from .quest import (
    QuestStore, approve_quest, edit_quest, evaluate_quest, propose_quest,
)
from .session import SessionStore
from .world_canon import CanonError, WorldStore, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-quest")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    proposal = sub.add_parser("propose")
    proposal.add_argument("--world-id", required=True)
    proposal.add_argument("--ending", required=True)
    proposal.add_argument("--title", required=True)
    proposal.add_argument("--description", required=True)
    for action in ("inspect", "edit", "approve", "compile", "verify", "progress"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action in ("edit", "approve", "compile"):
            cmd.add_argument("--expected-digest", required=True)
        if action == "edit":
            cmd.add_argument("--operation-file", required=True)
        if action == "approve":
            cmd.add_argument("--note", required=True)
        if action == "progress":
            cmd.add_argument("--slot", required=True)
    args = parser.parse_args(argv)
    try:
        store = QuestStore(args.store)
        world = WorldStore(args.store).read(args.world_id)
        if args.action == "propose":
            data = propose_quest(world, ending=args.ending,
                                 title=args.title, description=args.description)
            result = {"ok": True, "quest_digest": store.publish(
                args.world_id, data, create=True), "review_required": True}
        elif args.action == "inspect":
            data = store.read(args.world_id)
            result = {"ok": True, "quest_digest": digest(data), "quest": data}
        elif args.action == "edit":
            data = store.read(args.world_id)
            if digest(data) != args.expected_digest:
                raise CanonError("stale_quest")
            with open(args.operation_file, "rb") as stream:
                operation = strict_json(stream.read(524289))
            updated = edit_quest(data, world, operation)
            result = {"ok": True, "quest_digest": store.publish(
                args.world_id, updated, expected_digest=args.expected_digest),
                "review_required": True}
        elif args.action == "approve":
            data = store.read(args.world_id)
            if digest(data) != args.expected_digest:
                raise CanonError("stale_quest")
            updated = approve_quest(data, world, args.note)
            result = {"ok": True, "quest_digest": store.publish(
                args.world_id, updated, expected_digest=args.expected_digest),
                "review_required": False}
        elif args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, args.expected_digest)}
        elif args.action == "verify":
            result = {"ok": True, "receipt": store.verify(args.world_id)}
        else:
            data = store.read(args.world_id)
            if not data["approved"]:
                raise CanonError("quest_review_required")
            session = SessionStore(args.store).read(args.world_id, args.slot)
            result = {"ok": True, "progress": evaluate_quest(
                data, world, session["choices"])}
    except (CanonError, OSError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
