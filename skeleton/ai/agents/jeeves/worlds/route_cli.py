"""Operator CLI for source-bound world route review and verified playable handoff."""
from __future__ import annotations

import argparse
import json
import sys

from .route import RouteStore, approve_spec, propose_spec, solve
from .world_canon import CanonError, WorldStore, digest


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-route")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    propose = sub.add_parser("propose")
    propose.add_argument("--world-id", required=True)
    propose.add_argument("--ending", required=True)
    propose.add_argument("--require-flag", action="append", default=[])
    propose.add_argument("--forbid-flag", action="append", default=[])
    propose.add_argument("--forbid-choice", action="append", default=[])
    propose.add_argument("--max-steps", type=int, default=128)
    for action in ("inspect", "approve", "compile", "verify"):
        command = sub.add_parser(action)
        command.add_argument("--world-id", required=True)
        if action in ("approve", "compile"):
            command.add_argument("--expected-digest", required=True)
        if action == "approve":
            command.add_argument("--note", required=True)
    args = parser.parse_args(argv)
    try:
        store = RouteStore(args.store)
        world = WorldStore(args.store).read(args.world_id)
        if args.action == "propose":
            spec = propose_spec(
                world, ending=args.ending,
                requires_flags=args.require_flag,
                forbids_flags=args.forbid_flag,
                forbids_choices=args.forbid_choice,
                max_steps=args.max_steps,
            )
            lease = store.publish(args.world_id, spec, create=True)
            result = {
                "ok": True, "route_digest": lease, "world_digest": digest(world),
                "review_required": True, "spec": spec,
            }
        elif args.action == "inspect":
            spec = store.read(args.world_id)
            result = {
                "ok": True, "route_digest": digest(spec),
                "spec": spec, "review_required": not spec["approved"],
            }
            try:
                result["witness"] = list(solve(spec, world))
            except CanonError as exc:
                if exc.code not in {"route_unreachable", "route_search_inconclusive"}:
                    raise
                result["route_status"] = exc.code
        elif args.action == "approve":
            spec = store.read(args.world_id)
            if digest(spec) != args.expected_digest:
                raise CanonError("stale_route")
            reviewed = approve_spec(spec, world, args.note)
            lease = store.publish(args.world_id, reviewed,
                                  expected_digest=args.expected_digest)
            result = {"ok": True, "route_digest": lease,
                      "review_required": False}
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
