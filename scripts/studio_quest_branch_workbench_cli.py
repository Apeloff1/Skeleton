"""Source-leased quest branch preview, explicit approval, and private save."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_branch_workbench import (
    compile_branch_workbench, approve_branch_fork, compile_branch_handoff,
    publish_branch_checkpoint, restore_branch_checkpoint,
    render_branch_workbench_html,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review and commit one canonical quest fork")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-session", required=True)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--approval-file", type=Path)
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--review-html", action="store_true")
    parser.add_argument("--handoff", action="store_true")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args(argv)
    if args.restore is not None:
        if (args.plan_file is not None or args.approve or args.approval_file
                or args.review_html or args.publish or args.handoff):
            parser.error("restore is exclusive")
    elif args.plan_file is None:
        parser.error("--plan-file required unless restoring")
    if args.approve != (args.approval_file is not None):
        parser.error("--approve and --approval-file must be supplied together")
    if (args.review_html and (args.approve or args.publish or args.handoff)
            or not args.approve and (args.publish or args.handoff)):
        parser.error("review cannot publish; handoff and save require approval")
    try:
        docs = read_blueprint(args.project)
        if args.restore is not None:
            checkpoint = restore_branch_checkpoint(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
            if checkpoint["initial_session_digest"] != args.expected_session:
                raise StudioQuestError("stale quest fork restore session")
            result = {"schema": "skeleton.cli.studio_quest_branch_workbench.v1",
                      "checkpoint": checkpoint, "file_write_performed": False,
                      "release_certified": False}
        else:
            proposal = compile_branch_workbench(
                docs, read_studio_private_json(args.plan_file, 32768),
                authorized=True, expected_source_digest=args.expected_source,
                expected_initial_session_digest=args.expected_session)
            if args.review_html:
                print(render_branch_workbench_html(
                    docs, proposal, authorized=True).decode("utf-8"))
                return 0
            result = {"schema": "skeleton.cli.studio_quest_branch_workbench.v1",
                      "proposal": proposal, "file_write_performed": False,
                      "release_certified": False}
            if args.approve:
                checkpoint = approve_branch_fork(
                    docs, proposal, read_studio_private_json(
                        args.approval_file, 4096),
                    authorized=True, expected_source_digest=args.expected_source,
                    expected_initial_session_digest=args.expected_session)
                result["checkpoint"] = checkpoint
                if args.handoff:
                    result["playable_handoff"] = compile_branch_handoff(
                        docs, checkpoint, authorized=True)
                if args.publish is not None:
                    result["publication"] = publish_branch_checkpoint(
                        docs, checkpoint, args.publish, authorized=True)
                    result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
