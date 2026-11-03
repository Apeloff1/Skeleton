"""Operator CLI: preview -> reviewed JSON -> durable fork -> HTML5 handoff."""
from __future__ import annotations

import argparse
import json
import sys

from .branching import ForkStore
from .session_cli import _bounded_import
from .world_canon import CanonError


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-fork")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--world-id", required=True)
    preview.add_argument("--parent-slot", required=True)
    preview.add_argument("--target-slot", required=True)
    preview.add_argument("--prompt", required=True)
    preview.add_argument("--at-revision", type=int, required=True)
    preview.add_argument("--choice-id", required=True)
    publish = sub.add_parser("publish")
    publish.add_argument("--world-id", required=True)
    publish.add_argument("--proposal-file", required=True)
    publish.add_argument("--expected-parent-digest", required=True)
    for action in ("inspect", "compare", "compile"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        cmd.add_argument("--target-slot", required=True)
        if action == "compile":
            cmd.add_argument("--expected-world-digest", required=True)
    args = parser.parse_args(argv)
    try:
        store = ForkStore(args.store)
        if args.action == "preview":
            payload = store.preview(
                args.world_id, parent_slot=args.parent_slot,
                target_slot=args.target_slot, prompt=args.prompt,
                at_revision=args.at_revision, choice_id=args.choice_id)
        elif args.action == "publish":
            payload = store.publish(
                args.world_id, _bounded_import(args.proposal_file),
                args.expected_parent_digest)
        elif args.action == "inspect":
            payload = store.inspect(args.world_id, args.target_slot)
        elif args.action == "compare":
            payload = store.compare(args.world_id, args.target_slot)
        else:
            payload = store.compile(
                args.world_id, args.target_slot, args.expected_world_digest)
    except (CanonError, OSError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "result": payload},
                     sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
