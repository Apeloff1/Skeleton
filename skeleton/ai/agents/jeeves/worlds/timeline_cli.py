"""Author-reviewed temporal event CLI for source-bound world continuity."""
from __future__ import annotations

import argparse
import json
import sys

from .timeline import TimelineStore, edit_timeline, propose_timeline
from .world_canon import CanonError, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-timeline")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("propose")
    for field in ("world-id", "actor", "opening-note", "resolution-note"):
        plan.add_argument("--" + field, required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--world-id", required=True)
    patch = sub.add_parser("edit")
    patch.add_argument("--world-id", required=True)
    patch.add_argument("--expected-digest", required=True)
    patch.add_argument("--operation-file", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("--world-id", required=True)
    compile_cmd.add_argument("--expected-digest", required=True)
    args = parser.parse_args(argv)
    try:
        store = TimelineStore(args.store)
        if args.action == "propose":
            world = store.worlds.read(args.world_id)
            data = propose_timeline(world, actor=args.actor,
                                    opening_note=args.opening_note,
                                    resolution_note=args.resolution_note)
            result = {"ok": True, "timeline_digest":
                      store.publish(args.world_id, data, create=True),
                      "review_required": True}
        elif args.action == "inspect":
            data = store.read(args.world_id)
            result = {"ok": True, "timeline": data, "digest": digest(data)}
        elif args.action == "edit":
            with open(args.operation_file, "rb") as stream:
                operation = strict_json(stream.read(524289))
            world = store.worlds.read(args.world_id)
            data = store.read(args.world_id)
            if digest(data) != args.expected_digest:
                raise CanonError("stale_timeline")
            updated = edit_timeline(data, world, operation)
            result = {"ok": True, "timeline_digest":
                      store.publish(args.world_id, updated,
                                    expected_digest=args.expected_digest)}
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
