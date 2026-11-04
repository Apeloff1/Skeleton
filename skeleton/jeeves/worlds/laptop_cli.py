"""Operator CLI: prompt -> typed proposal -> reviewed edit -> verified playable."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys

from .laptop_flow import LaptopFlow
from .world_canon import CanonError, strict_json

MAX_INPUT = 524288


def _file(path: str):
    """Read bounded JSON through descriptor-anchored, no-symlink path traversal.

    Every directory component is opened relative to the previous directory
    descriptor. A rename of a parent after opening cannot redirect the read.
    """
    if not all(hasattr(os, name) for name in ("O_NONBLOCK", "O_NOFOLLOW", "O_DIRECTORY")):
        raise CanonError("input_safe_open_unavailable")
    if not isinstance(path, str) or not path or chr(0) in path:
        raise CanonError("input_invalid_path")
    parts = path.split("/")
    absolute = path.startswith("/")
    if absolute:
        parts = parts[1:]
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise CanonError("input_invalid_path")
    directory_flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                       getattr(os, "O_CLOEXEC", 0) | os.O_NONBLOCK)
    file_flags = (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                  getattr(os, "O_CLOEXEC", 0))
    directory = os.open("/" if absolute else ".", directory_flags)
    try:
        for part in parts[:-1]:
            next_directory = os.open(part, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        fd = os.open(parts[-1], file_flags, dir_fd=directory)
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise CanonError("input_not_regular")
            if metadata.st_size > MAX_INPUT:
                raise CanonError("input_too_large")
            with os.fdopen(os.dup(fd), "rb") as handle:
                data = handle.read(MAX_INPUT + 1)
            if len(data) > MAX_INPUT:
                raise CanonError("input_too_large")
            return strict_json(data)
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-laptop")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    propose = sub.add_parser("propose")
    propose.add_argument("--brief-file", required=True)
    for name in ("inspect", "review", "approve-current", "compile", "verify", "diagnose", "acceptance",
                 "engine-inspect", "engine-compile", "engine-verify",
                 "session-create", "session-choose", "session-inspect",
                 "session-export", "session-restore", "session-restore-check"):
        command = sub.add_parser(name)
        command.add_argument("--world-id", required=True)
        if name in ("diagnose", "acceptance"):
            command.add_argument("--slot")
        elif name == "review":
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
            if name != "session-restore-check":
                command.add_argument("--slot", required=True)
            if name == "session-choose":
                command.add_argument("--choice-id", required=True)
                command.add_argument("--expected-session-digest", required=True)
            if name in ("session-restore", "session-restore-check"):
                command.add_argument("--export-file", required=True)
    args = parser.parse_args(argv)
    try:
        flow = LaptopFlow(args.store)
        if args.action == "propose":
            result = flow.propose(_file(args.brief_file))
        elif args.action == "inspect":
            result = flow.inspect(args.world_id)
        elif args.action == "diagnose":
            result = flow.diagnose(args.world_id, args.slot)
        elif args.action == "acceptance":
            result = flow.acceptance(args.world_id, args.slot)
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
        elif args.action == "session-restore-check":
            result = flow.preflight_restore(args.world_id, _file(args.export_file))
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
            "session_replay_mismatch": "reject_save_with_invalid_replay_and_use_trusted_copy",
            "session_export_schema_mismatch": "inspect_export_schema_and_use_trusted_copy",
            "session_already_exists": "select_an_unused_slot_without_overwriting",
            "laptop_builder_mismatch": "recompile_and_verify_from_reviewed_source",
            "laptop_html_mismatch": "recompile_and_verify_from_reviewed_source",
            "laptop_receipt_mismatch": "recompile_and_verify_from_reviewed_source",
            "lease_busy": "retry_after_current_writer_finishes",
            "laptop_source_changed_after_verify": "retry_after_source_edit_and_recompile",
            "laptop_acceptance_budget": "reduce_world_complexity_before_acceptance",
            "laptop_acceptance_session_mismatch": "inspect_session_and_reverify_export",
            "laptop_acceptance_ending_mismatch": "inspect_canonical_ending_witnesses",
            "laptop_acceptance_restore_mismatch": "reject_roundtrip_and_inspect_session_contract",
            "laptop_engine_source_mismatch": "reinspect_laptop_and_engine_sources_before_retry",
            "laptop_engine_stale_source": "reinspect_engine_source_digests_before_compile",
            "laptop_engine_verify_mismatch": "reject_engine_handoff_and_reverify_exact_sources",
        }
        print(json.dumps({"ok": False, "error": code, "phase": args.action,
                          "next_action": recovery.get(code, "inspect_input_and_custody")},
                         sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "result": result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
