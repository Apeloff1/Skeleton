"""Offline quest replay recovery preview and explicitly selected repair."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_replay_repair import (
    compile_replay_repair, approve_replay_repair, render_replay_repair_html,
)
from skeleton.ai.game_builder.studio_quest_replay_diagnostic import (
    compile_replay_diagnostic_handoff, publish_replay_diagnostic,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rehearse bounded quest recovery; explicitly approve one replay candidate")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-session", required=True)
    parser.add_argument("--plan-file", type=Path, required=True)
    parser.add_argument("--approval-file", type=Path)
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--review-html", action="store_true")
    parser.add_argument("--handoff", action="store_true")
    parser.add_argument("--publish", type=Path)
    args = parser.parse_args(argv)
    if args.approve != (args.approval_file is not None):
        parser.error("--approve and --approval-file are required together")
    if (args.review_html and (args.approve or args.handoff or args.publish)
            or not args.approve and (args.handoff or args.publish)):
        parser.error("unapproved quest recovery cannot publish or handoff")
    try:
        docs = read_blueprint(args.project)
        proposal = compile_replay_repair(
            docs, read_studio_private_json(args.plan_file, 32768), authorized=True,
            expected_source_digest=args.expected_source,
            expected_initial_session_digest=args.expected_session)
        if args.review_html:
            print(render_replay_repair_html(
                docs, proposal, authorized=True).decode("utf-8"))
            return 0
        result: dict[str, object] = {
            "schema": "skeleton.cli.studio_quest_replay_repair.v1",
            "proposal": proposal, "file_write_performed": False,
            "release_certified": False,
        }
        if args.approve:
            diagnostic = approve_replay_repair(
                docs, proposal, read_studio_private_json(args.approval_file, 4096),
                authorized=True, expected_source_digest=args.expected_source,
                expected_initial_session_digest=args.expected_session)
            result["diagnostic"] = diagnostic
            if args.handoff:
                result["playable_handoff"] = compile_replay_diagnostic_handoff(
                    docs, diagnostic, authorized=True)
            if args.publish:
                result["publication"] = publish_replay_diagnostic(
                    docs, diagnostic, args.publish, authorized=True)
                result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
