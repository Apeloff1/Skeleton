"""Operator CLI: prompt -> typed proposal -> reviewed edit -> verified playable."""
from __future__ import annotations

import argparse
import json
import sys

from .laptop_flow import LaptopFlow
from .world_canon import CanonError, strict_json

MAX_INPUT = 524288


def _file(path: str):
    with open(path, "rb") as handle:
        return strict_json(handle.read(MAX_INPUT + 1))


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-laptop")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    propose = sub.add_parser("propose")
    propose.add_argument("--brief-file", required=True)
    for name in ("inspect", "review", "approve-current", "compile", "verify",
                 "engine-inspect", "engine-compile", "engine-verify",
                 "session-create", "session-choose", "session-inspect",
                 "session-export", "session-restore"):
        command = sub.add_parser(name)
        command.add_argument("--world-id", required=True)
        if name == "review":
            command.add_argument("--expected-digest", required=True)
            command.add_argument("--operation-file", required=True)
            command.add_argument("--review-note", required=True)
        elif name == "approve-current":
            command.add_argument("--expected-digest", required=True)
            command.add_argument("--review-note", required=True)
        elif name in ("engine-inspect", "engine-compile"):
            command.add_argument("--era", required=True)
            if name == "engine-compile":
                command.add_argument("--expected-digests-file", required=True)
        elif name == "compile":
            command.add_argument("--expected-digest", required=True)
        elif name.startswith("session-"):
            command.add_argument("--slot", required=True)
            if name == "session-choose":
                command.add_argument("--choice-id", required=True)
                command.add_argument("--expected-session-digest", required=True)
            if name == "session-restore":
                command.add_argument("--export-file", required=True)
    args = parser.parse_args(argv)
    try:
        flow = LaptopFlow(args.store)
        if args.action == "propose":
            result = flow.propose(_file(args.brief_file))
        elif args.action == "inspect":
            result = flow.inspect(args.world_id)
        elif args.action == "review":
            result = flow.review(args.world_id, args.expected_digest,
                                 _file(args.operation_file), args.review_note)
        elif args.action == "approve-current":
            result = flow.approve_current(args.world_id, args.expected_digest,
                                          args.review_note)
        elif args.action == "engine-inspect":
            result = flow.engine_inspect(args.world_id, args.era)
        elif args.action == "engine-compile":
            result = flow.engine_compile(args.world_id, args.era,
                                         _file(args.expected_digests_file))
        elif args.action == "engine-verify":
            result = flow.engine_verify(args.world_id)
        elif args.action == "compile":
            result = flow.compile(args.world_id, args.expected_digest)
        elif args.action == "verify":
            result = flow.verify(args.world_id)
        elif args.action == "session-create":
            result = flow.create_session(args.world_id, args.slot)
        elif args.action == "session-restore":
            result = flow.create_session(args.world_id, args.slot,
                                         imported=_file(args.export_file))
        elif args.action == "session-choose":
            result = flow.choose(args.world_id, args.slot, args.choice_id,
                                 args.expected_session_digest)
        elif args.action == "session-inspect":
            result = flow.inspect_session(args.world_id, args.slot)
        else:
            result = flow.export_session(args.world_id, args.slot)
    except (CanonError, OSError, ValueError, TypeError, OverflowError) as exc:
        code = exc.code if isinstance(exc, CanonError) else "invalid_input"
        recovery = {
            "stale_source": "inspect_source_and_repeat_review",
            "review_stale_source": "inspect_source_and_repeat_review",
            "review_required": "review_source_before_compile",
            "stale_session": "inspect_session_and_retry_with_latest_digest",
            "session_world_lease_mismatch": "reconcile_source_revision_before_restore",
            "session_checksum_mismatch": "reject_export_and_restore_from_trusted_copy",
            "laptop_builder_mismatch": "recompile_and_verify_from_reviewed_source",
            "laptop_html_mismatch": "recompile_and_verify_from_reviewed_source",
            "laptop_receipt_mismatch": "recompile_and_verify_from_reviewed_source",
            "lease_busy": "retry_after_current_writer_finishes",
        }
        print(json.dumps({"ok": False, "error": code, "phase": args.action,
                          "next_action": recovery.get(code, "inspect_input_and_custody")},
                         sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "result": result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
