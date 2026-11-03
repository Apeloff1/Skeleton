"""Operator-reviewed original NPC itinerary authoring and playable handoff."""
from __future__ import annotations

import argparse
import json
import sys

from .cast import CastStore
from .npc_schedule import ScheduleStore, edit_schedule
from .world_canon import CanonError, WorldStore, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-npc-schedule")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in (
        "propose", "inspect", "save", "edit", "editor", "approve", "compile", "verify",
    ):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "propose":
            for field in ("prompt", "actor", "scene", "label"):
                cmd.add_argument("--" + field, required=True)
            cmd.add_argument("--first-tick", type=int, required=True)
            cmd.add_argument("--last-tick", type=int, required=True)
        if action in ("save", "edit", "editor", "approve", "compile"):
            cmd.add_argument("--expected-digest")
        if action == "save":
            cmd.add_argument("--schedule-json", required=True)
            cmd.add_argument("--create", action="store_true")
        if action == "edit":
            cmd.add_argument("--operation-json", required=True)
        if action == "approve":
            cmd.add_argument("--review-note", required=True)
    args = parser.parse_args(argv)
    try:
        store = ScheduleStore(args.store)
        if args.action == "propose":
            result = {"proposal": store.propose(
                args.world_id, prompt=args.prompt, actor=args.actor,
                scene=args.scene, first_tick=args.first_tick,
                last_tick=args.last_tick, label=args.label,
            ), "review_required": True}
        elif args.action == "inspect":
            result = store.inspect(args.world_id)
        elif args.action == "save":
            source = strict_json(args.schedule_json.encode("utf-8"))
            result = {"schedule_digest": store.publish(
                args.world_id, source, expected_digest=args.expected_digest,
                create=args.create,
            ), "review_required": True}
        elif args.action == "edit":
            current = store.inspect(args.world_id)["schedule"]
            if digest(current) != args.expected_digest:
                raise CanonError("npc_schedule_stale_edit")
            world = WorldStore(args.store).read(args.world_id)
            cast = CastStore(args.store).read(args.world_id)
            updated = edit_schedule(
                current, world, cast,
                strict_json(args.operation_json.encode("utf-8")),
            )
            result = {"schedule_digest": store.publish(
                args.world_id, updated, expected_digest=args.expected_digest,
            ), "review_required": True}
        elif args.action == "editor":
            result = {"editor": store.editor(
                args.world_id, args.expected_digest,
            )}
        elif args.action == "approve":
            result = {"schedule_digest": store.approve(
                args.world_id, expected_digest=args.expected_digest,
                review_note=args.review_note,
            ), "review_required": False}
        elif args.action == "compile":
            result = {"receipt": store.compile(
                args.world_id, args.expected_digest,
            )}
        else:
            result = {"receipt": store.verify(args.world_id)}
    except (CanonError, OSError, UnicodeError) as exc:
        print(json.dumps({
            "ok": False,
            "error": exc.code if isinstance(exc, CanonError) else "io_error",
        }, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
