"""Reviewed original multi-world portal network CLI."""
from __future__ import annotations

import argparse
import json
import sys

from .portals import PortalStore
from .world_canon import CanonError, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-portals")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "inspect", "save", "editor", "approve", "compile", "verify", "record-session", "verify-session"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--network-id", required=True)
        if action == "propose":
            cmd.add_argument("--prompt", required=True)
            cmd.add_argument("--root-world", required=True)
            cmd.add_argument("--from-ending", required=True)
            cmd.add_argument("--to-world", required=True)
        if action == "save":
            cmd.add_argument("--network-json", required=True)
            cmd.add_argument("--expected-network-digest")
            cmd.add_argument("--create", action="store_true")
        if action in ("editor", "approve", "compile"):
            cmd.add_argument("--expected-network-digest", required=True)
        if action == "approve":
            cmd.add_argument("--review-note", required=True)
        if action in ("record-session", "verify-session"):
            cmd.add_argument("--slot", required=True)
        if action == "record-session":
            cmd.add_argument("--session-json", required=True)
            cmd.add_argument("--expected-network-digest", required=True)
            cmd.add_argument("--expected-session-digest")
            cmd.add_argument("--create", action="store_true")
    args = parser.parse_args(argv)
    try:
        store = PortalStore(args.store)
        if args.action == "propose":
            result = {"proposal": store.propose(
                args.network_id, args.prompt, root_world=args.root_world,
                from_ending=args.from_ending, to_world=args.to_world,
            )}
        elif args.action == "inspect":
            result = store.inspect(args.network_id)
        elif args.action == "save":
            result = {"network_digest": store.save(
                args.network_id, strict_json(args.network_json.encode("utf-8")),
                expected_network_digest=args.expected_network_digest,
                create=args.create,
            )}
        elif args.action == "editor":
            result = {"editor": store.editor(
                args.network_id, expected_network_digest=args.expected_network_digest,
            )}
        elif args.action == "approve":
            result = {"network_digest": store.approve(
                args.network_id, expected_network_digest=args.expected_network_digest,
                review_note=args.review_note,
            )}
        elif args.action == "compile":
            result = {"receipt": store.compile(
                args.network_id, expected_network_digest=args.expected_network_digest,
            )}
        elif args.action == "record-session":
            result = {"result": store.record_session(
                args.network_id, args.slot,
                strict_json(args.session_json.encode("utf-8")),
                expected_network_digest=args.expected_network_digest,
                expected_session_digest=args.expected_session_digest,
                create=args.create,
            )}
        elif args.action == "verify-session":
            result = {"result": store.verify_session(args.network_id, args.slot)}
        else:
            result = {"receipt": store.verify(args.network_id)}
    except (CanonError, OSError, UnicodeError) as exc:
        print(json.dumps({
            "ok": False,
            "error": exc.code if isinstance(exc, CanonError) else "io_error",
        }, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
