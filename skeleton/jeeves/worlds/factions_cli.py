"""Operator CLI for reviewed, source-bound faction reputation."""
from __future__ import annotations

import argparse
import json
import sys

from .factions import (
    FactionStore, approve_factions, edit_factions, propose_factions,
)
from .world_canon import CanonError, WorldStore, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-factions")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    proposal = sub.add_parser("propose")
    for name in ("world-id", "prompt", "faction-id", "name", "description",
                 "choice-id", "reason"):
        proposal.add_argument("--" + name, required=True)
    proposal.add_argument("--delta", type=int, required=True)
    for action in ("inspect", "edit", "approve", "compile", "verify", "player"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action in ("edit", "approve", "compile"):
            cmd.add_argument("--expected-digest", required=True)
        if action == "edit":
            cmd.add_argument("--operation-json", required=True)
        if action == "approve":
            cmd.add_argument("--note", required=True)
        if action == "player":
            cmd.add_argument("--slot", required=True)
    args = parser.parse_args(argv)
    try:
        store = FactionStore(args.store)
        if args.action == "verify":
            result = {"ok": True, "receipt": store.verify(args.world_id)}
        elif args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, args.expected_digest)}
        elif args.action == "player":
            result = {"ok": True, "player": store.player(args.world_id, args.slot)}
        else:
            world = WorldStore(args.store).read(args.world_id)
            if args.action == "propose":
                data = propose_factions(
                    world, prompt=args.prompt, faction_id=args.faction_id,
                    name=args.name, description=args.description,
                    choice_id=args.choice_id, delta=args.delta,
                    reason=args.reason)
                result = {"ok": True, "factions_digest": store.publish(
                    args.world_id, data, create=True), "review_required": True}
            else:
                data = store.read(args.world_id)
                if args.action == "inspect":
                    result = {"ok": True, "factions_digest": digest(data),
                              "factions": data}
                else:
                    if digest(data) != args.expected_digest:
                        raise CanonError("stale_factions")
                    updated = (edit_factions(
                        data, world, strict_json(args.operation_json.encode("utf-8")))
                        if args.action == "edit" else
                        approve_factions(data, world, args.note))
                    result = {"ok": True, "factions_digest": store.publish(
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
