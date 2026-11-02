"""Source-leased quest remap preview, offline review and explicit approval."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_npc_knowledge_relay_cli import _private_json
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_remap_proposal import (
    compile_quest_remap_proposal, approve_quest_remap_proposal,
    render_quest_remap_review_html,
)
from skeleton.ai.game_builder.studio_quest_revision_migration import (
    compile_quest_migration_handoff, publish_quest_revision_migration,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview source-bound quest remaps; approve only by explicit operator action")
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
        parser.error("--approve and --approval-file must be supplied together")
    if (args.review_html and (args.approve or args.publish or args.handoff)
            or not args.approve and (args.publish or args.handoff)):
        parser.error("review cannot publish; handoff and publication require approval")
    try:
        docs = read_blueprint(args.project)
        proposal = compile_quest_remap_proposal(
            docs, _private_json(args.plan_file, 32768), authorized=True,
            expected_source_digest=args.expected_source,
            expected_initial_session_digest=args.expected_session)
        if args.review_html:
            print(render_quest_remap_review_html(
                docs, proposal, authorized=True).decode("utf-8"))
            return 0
        result: dict[str, object] = {
            "schema": "skeleton.cli.studio_quest_remap_proposal.v1",
            "proposal": proposal, "file_write_performed": False,
            "release_certified": False,
        }
        if args.approve:
            migration = approve_quest_remap_proposal(
                docs, proposal, _private_json(args.approval_file, 32768),
                authorized=True, expected_source_digest=args.expected_source,
                expected_initial_session_digest=args.expected_session)
            result["migration"] = migration
            if args.handoff:
                result["playable_handoff"] = compile_quest_migration_handoff(
                    docs, migration, authorized=True)
            if args.publish:
                result["publication"] = publish_quest_revision_migration(
                    docs, migration, args.publish, authorized=True)
                result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
