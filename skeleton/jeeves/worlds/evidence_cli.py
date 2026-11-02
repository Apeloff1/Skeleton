"""Operator CLI for original, source-bound player clue discovery."""
from __future__ import annotations

import argparse
import json
import sys

from .evidence import (
    EvidenceStore, approve_evidence, edit_evidence, propose_evidence,
)
from .world_canon import CanonError, WorldStore, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-evidence")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    proposal = sub.add_parser("propose")
    for field in ("world-id", "prompt", "clue-id", "title", "detail",
                  "unlock-choice"):
        proposal.add_argument("--" + field, required=True)
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
        store = EvidenceStore(args.store)
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
                data = propose_evidence(
                    world, prompt=args.prompt, clue_id=args.clue_id,
                    title=args.title, detail=args.detail,
                    unlock_choice=args.unlock_choice)
                result = {"ok": True, "evidence_digest": store.publish(
                    args.world_id, data, create=True), "review_required": True}
            else:
                data = store.read(args.world_id)
                if args.action == "inspect":
                    result = {"ok": True, "evidence_digest": digest(data),
                              "evidence": data}
                else:
                    if digest(data) != args.expected_digest:
                        raise CanonError("stale_evidence")
                    updated = (edit_evidence(
                        data, world, strict_json(args.operation_json.encode("utf-8")))
                        if args.action == "edit" else
                        approve_evidence(data, world, args.note))
                    result = {"ok": True, "evidence_digest": store.publish(
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
