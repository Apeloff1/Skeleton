"""Reviewed original NPC/dialogue authoring, edit and playable compilation."""
from __future__ import annotations

import argparse
import json
import sys

from .cast import CastStore, approve_cast, edit_cast, propose_cast
from .world_canon import CanonError, WorldStore, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-cast")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    proposal = sub.add_parser("propose")
    proposal.add_argument("--world-id", required=True)
    proposal.add_argument("--npc-id", required=True)
    proposal.add_argument("--npc-name", required=True)
    proposal.add_argument("--npc-line", required=True)
    for action in ("inspect", "edit", "approve", "compile", "verify"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action in ("edit", "approve", "compile"):
            cmd.add_argument("--expected-digest", required=True)
        if action == "edit":
            cmd.add_argument("--operation-file", required=True)
        if action == "approve":
            cmd.add_argument("--note", required=True)
    args = parser.parse_args(argv)
    try:
        store = CastStore(args.store)
        world = WorldStore(args.store).read(args.world_id)
        if args.action == "propose":
            data = propose_cast(world, npc_id=args.npc_id,
                                npc_name=args.npc_name, npc_line=args.npc_line)
            lease = store.publish(args.world_id, data, create=True)
            result = {"ok": True, "cast_digest": lease,
                      "review_required": True, "cast": data}
        elif args.action == "inspect":
            data = store.read(args.world_id)
            result = {"ok": True, "cast_digest": digest(data),
                      "review_required": not data["approved"], "cast": data}
        elif args.action == "edit":
            data = store.read(args.world_id)
            if digest(data) != args.expected_digest:
                raise CanonError("stale_cast")
            with open(args.operation_file, "rb") as stream:
                operation = strict_json(stream.read(524289))
            updated = edit_cast(data, world, operation)
            lease = store.publish(args.world_id, updated,
                                  expected_digest=args.expected_digest)
            result = {"ok": True, "cast_digest": lease, "review_required": True}
        elif args.action == "approve":
            data = store.read(args.world_id)
            if digest(data) != args.expected_digest:
                raise CanonError("stale_cast")
            updated = approve_cast(data, world, args.note)
            lease = store.publish(args.world_id, updated,
                                  expected_digest=args.expected_digest)
            result = {"ok": True, "cast_digest": lease, "review_required": False}
        elif args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, args.expected_digest)}
        else:
            result = {"ok": True, "receipt": store.verify(args.world_id)}
    except (CanonError, OSError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
