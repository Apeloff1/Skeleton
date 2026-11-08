"""Reviewed save migration CLI: preview first, apply only with exact lease."""
from __future__ import annotations

import argparse
import json
import sys

from .migration import MigrationStore
from .session_cli import _bounded_import
from .world_canon import CanonError, digest


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-migrate")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("preview", "apply"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        cmd.add_argument("--old-world-file", required=True)
        cmd.add_argument("--checkpoint-file", required=True)
        cmd.add_argument("--choice-map-file")
        if action == "apply":
            cmd.add_argument("--slot", required=True)
            cmd.add_argument("--expected-preview-digest", required=True)
            cmd.add_argument("--review-note", required=True)
    args = parser.parse_args(argv)
    try:
        old_world = _bounded_import(args.old_world_file)
        checkpoint = _bounded_import(args.checkpoint_file)
        choice_map = (_bounded_import(args.choice_map_file)
                      if args.choice_map_file else {})
        store = MigrationStore(args.store)
        if args.action == "preview":
            preview = store.preview(args.world_id, old_world, checkpoint, choice_map)
            result = {"ok": True, "preview": preview, "preview_digest": digest(preview)}
        else:
            receipt = store.apply(
                args.world_id, args.slot, old_world, checkpoint, choice_map,
                expected_preview_digest=args.expected_preview_digest,
                review_note=args.review_note)
            result = {"ok": True, "receipt": receipt}
    except (CanonError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
