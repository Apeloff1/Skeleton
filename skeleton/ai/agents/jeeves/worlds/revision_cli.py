"""Operator review of canonical world revisions with verified playable handoff."""
from __future__ import annotations

import argparse
import json
import sys

from .revision import RevisionStore
from .session_cli import _bounded_import
from .world_canon import CanonError, digest


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-revision")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("preview", "review", "verify"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        cmd.add_argument("--old-world-file", required=True)
        if action == "review":
            cmd.add_argument("--expected-impact-digest", required=True)
            cmd.add_argument("--review-note", required=True)
    args = parser.parse_args(argv)
    try:
        old = _bounded_import(args.old_world_file)
        store = RevisionStore(args.store)
        if args.action == "preview":
            report = store.preview(args.world_id, old)
            result = {"ok": True, "impact": report, "impact_digest": digest(report)}
        elif args.action == "review":
            result = {"ok": True, "receipt": store.review(
                args.world_id, old, expected_impact_digest=args.expected_impact_digest,
                note=args.review_note)}
        else:
            result = {"ok": True, "receipt": store.verify(args.world_id, old)}
    except (CanonError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
