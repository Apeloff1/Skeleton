"""Operator-only source-leased counterfactual authoring, review and compilation."""
from __future__ import annotations

import argparse
import json
import sys

from .counterfactual import (
    CounterfactualStore, approve_review, build_report, edit_review, propose_review,
)
from .session import SessionStore
from .world_canon import CanonError, WorldStore, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-counterfactual")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "inspect", "edit", "preview", "approve", "compile", "verify"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        cmd.add_argument("--slot", required=True)
        if action == "propose":
            cmd.add_argument("--prompt", required=True)
            cmd.add_argument("--max-steps", type=int, default=128)
            cmd.add_argument("--max-variants", type=int, default=64)
        if action in ("edit", "approve", "compile"):
            cmd.add_argument("--expected-digest", required=True)
        if action == "edit":
            cmd.add_argument("--operation-json", required=True)
        if action == "approve":
            cmd.add_argument("--note", required=True)
    args = parser.parse_args(argv)
    try:
        store = CounterfactualStore(args.store)
        if args.action == "verify":
            result = {"ok": True, "receipt": store.verify(args.world_id, args.slot)}
        elif args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, args.slot, args.expected_digest)}
        else:
            world = WorldStore(args.store).read(args.world_id)
            session = SessionStore(args.store).read(args.world_id, args.slot)
            if args.action == "propose":
                review = propose_review(
                    world, session, slot=args.slot, prompt=args.prompt,
                    max_steps=args.max_steps, max_variants=args.max_variants,
                )
                revision = store.publish(args.world_id, args.slot, review, create=True)
                result = {"ok": True, "review_digest": revision,
                          "review_required": True}
            else:
                review = store.read(args.world_id, args.slot)
                if args.action == "inspect":
                    result = {"ok": True, "review_digest": digest(review), "review": review}
                elif args.action == "preview":
                    result = {"ok": True, "report": build_report(review, world, session),
                              "review_required": not review["approved"]}
                else:
                    if digest(review) != args.expected_digest:
                        raise CanonError("stale_counterfactual")
                    if args.action == "edit":
                        operation = strict_json(args.operation_json.encode("utf-8"))
                        updated = edit_review(review, world, session, operation)
                    else:
                        updated = approve_review(review, world, session, args.note)
                    revision = store.publish(
                        args.world_id, args.slot, updated,
                        expected_digest=args.expected_digest,
                    )
                    result = {"ok": True, "review_digest": revision,
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
