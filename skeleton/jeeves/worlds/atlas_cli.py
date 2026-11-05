"""Operator-owned original region atlas workflow and verified playable handoff."""
from __future__ import annotations

import argparse
import json
import sys

from .atlas import AtlasStore
from .world_canon import CanonError, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-atlas")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "inspect", "save", "editor", "approve", "compile", "verify"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "propose":
            cmd.add_argument("--prompt", required=True)
        if action == "save":
            cmd.add_argument("--atlas-json", required=True)
            cmd.add_argument("--expected-world-digest", required=True)
            cmd.add_argument("--expected-atlas-digest")
            cmd.add_argument("--create", action="store_true")
        if action in ("editor", "approve", "compile"):
            cmd.add_argument("--expected-atlas-digest", required=True)
        if action == "approve":
            cmd.add_argument("--review-note", required=True)
    args = parser.parse_args(argv)
    try:
        store = AtlasStore(args.store)
        if args.action == "propose":
            result = {"proposal": store.propose(args.world_id, args.prompt)}
        elif args.action == "inspect":
            result = store.inspect(args.world_id)
        elif args.action == "save":
            spec = strict_json(args.atlas_json.encode("utf-8"))
            result = {"atlas_digest": store.save(
                args.world_id, spec,
                expected_world_digest=args.expected_world_digest,
                expected_atlas_digest=args.expected_atlas_digest,
                create=args.create,
            )}
        elif args.action == "editor":
            result = {"editor": store.editor(
                args.world_id, expected_atlas_digest=args.expected_atlas_digest,
            )}
        elif args.action == "approve":
            result = {"atlas_digest": store.approve(
                args.world_id, expected_atlas_digest=args.expected_atlas_digest,
                review_note=args.review_note,
            )}
        elif args.action == "compile":
            result = {"receipt": store.compile(
                args.world_id, expected_atlas_digest=args.expected_atlas_digest,
            )}
        else:
            result = {"receipt": store.verify(args.world_id)}
    except (CanonError, OSError, UnicodeError) as exc:
        print(json.dumps({
            "ok": False, "error": (
                exc.code if isinstance(exc, CanonError) else "io_error"
            ),
        }, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
