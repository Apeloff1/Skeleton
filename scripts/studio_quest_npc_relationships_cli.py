"""CLI for original NPC trust consequences of canonical authored choices."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_npc_relationships import (
    PROMPT, propose_quest_npc_relationships, compile_quest_npc_relationships,
    compile_npc_relationship_handoff, render_npc_relationship_editor_html,
    publish_npc_relationships, restore_npc_relationships,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Author canonical quest NPC relationships")
    parser.add_argument("--project", required=True)
    parser.add_argument("--actor", action="append", default=[])
    parser.add_argument("--actions", type=Path)
    parser.add_argument("--target-ending")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--handoff", action="store_true")
    parser.add_argument("--editor-html", action="store_true")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args(argv)
    if args.editor_html and (args.handoff or args.publish or args.restore):
        parser.error("editor HTML is read-only")
    if args.publish and args.restore:
        parser.error("cannot publish and restore together")
    if args.plan and (args.actor or args.actions or args.target_ending):
        parser.error("provide an edited plan or proposal inputs, not both")
    if not args.plan and not args.restore and (
            not args.actor or not args.actions or not args.target_ending):
        parser.error("proposal requires actor IDs, actions and ending")
    try:
        docs = read_blueprint(args.project)
        program = compile_quest_program(docs)
        initial = start_quest(docs, authorized=True)
        if args.restore:
            receipt = restore_npc_relationships(
                docs, args.restore, authorized=True,
                expected_source_digest=program.source_digest)
        else:
            if args.plan:
                plan = read_studio_private_json(args.plan, 131072)
            else:
                actions = read_studio_private_json(args.actions, 65536)
                plan = propose_quest_npc_relationships(
                    docs, PROMPT, args.actor, actions, args.target_ending,
                    authorized=True, expected_source_digest=program.source_digest,
                    expected_initial_session_digest=initial.digest)
            receipt = compile_quest_npc_relationships(
                docs, plan, authorized=True,
                expected_source_digest=program.source_digest,
                expected_initial_session_digest=initial.digest)
        if args.editor_html:
            print(render_npc_relationship_editor_html(
                docs, receipt, authorized=True).decode("utf-8"))
            return 0
        result = {"schema": "skeleton.cli.studio_quest_npc_relationships.v1",
                  "relationships": receipt, "file_write_performed": False,
                  "release_certified": False}
        if args.handoff:
            result["playable_handoff"] = compile_npc_relationship_handoff(
                docs, receipt, authorized=True)
        if args.publish:
            result["publication"] = publish_npc_relationships(
                docs, receipt, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
