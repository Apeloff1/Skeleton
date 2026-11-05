"""Operator-gated typed Jeeves production plan CLI."""
from __future__ import annotations

import argparse
import json
import sys

from .plan import PlanStore, _sources, propose_plan, review_task
from .world_canon import CanonError, digest


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-plan")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("propose", "inspect", "compile"):
        command = sub.add_parser(name)
        command.add_argument("--world-id", required=True)
        if name == "compile":
            command.add_argument("--expected-digest", required=True)
    review = sub.add_parser("review")
    review.add_argument("--world-id", required=True)
    review.add_argument("--expected-digest", required=True)
    review.add_argument("--task-id", required=True)
    review.add_argument("--decision", required=True, choices=("approved", "blocked"))
    review.add_argument("--note", required=True)
    args = parser.parse_args(argv)
    try:
        store = PlanStore(args.store)
        if args.action == "propose":
            fd = store.worlds._directory()
            try:
                world, assets, timeline = _sources(fd, store.worlds, args.world_id)
            finally:
                import os
                os.close(fd)
            plan = propose_plan(world, assets, timeline)
            result = {"ok": True, "plan_digest":
                      store.publish(args.world_id, plan, create=True),
                      "tasks": len(plan["tasks"]), "review_required": True}
        elif args.action == "inspect":
            plan = store.read(args.world_id)
            result = {"ok": True, "plan": plan, "digest": digest(plan)}
        elif args.action == "review":
            fd = store.worlds._directory()
            try:
                world, assets, timeline = _sources(fd, store.worlds, args.world_id)
            finally:
                import os
                os.close(fd)
            plan = store.read(args.world_id)
            if digest(plan) != args.expected_digest:
                raise CanonError("stale_plan")
            updated = review_task(plan, world, assets, timeline,
                                  task_id=args.task_id, decision=args.decision,
                                  note=args.note)
            result = {"ok": True, "plan_digest": store.publish(
                args.world_id, updated, expected_digest=args.expected_digest)}
        else:
            result = {"ok": True, **store.compile(args.world_id, args.expected_digest)}
    except (CanonError, OSError) as exc:
        print(json.dumps({"ok": False, "error": exc.code if isinstance(exc, CanonError)
                          else "io_error"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
