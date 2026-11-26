"""CLI for operator-reviewed original NPC dialogue translations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_dialogue_localization import (
    PROMPT, propose_dialogue_localization, compile_dialogue_localization,
    compile_dialogue_localized_handoff, render_dialogue_localization_editor_html,
    publish_dialogue_localization, restore_dialogue_localization,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review original NPC dialogue translations")
    parser.add_argument("--project", required=True)
    parser.add_argument("--npc-file", type=Path, required=True)
    parser.add_argument("--dialogue-file", type=Path, required=True)
    parser.add_argument("--locale")
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
    if args.plan and args.locale:
        parser.error("provide either a reviewed plan or locale proposal")
    if not args.plan and not args.restore and not args.locale:
        parser.error("proposal requires a locale")
    try:
        docs = read_blueprint(args.project)
        program = compile_quest_program(docs)
        initial = start_quest(docs, authorized=True)
        npc = read_studio_private_json(args.npc_file, 196608)
        dialogue = read_studio_private_json(args.dialogue_file, 262144)
        if args.restore:
            receipt = restore_dialogue_localization(
                docs, npc, dialogue, args.restore, authorized=True,
                expected_source_digest=program.source_digest)
        else:
            plan = (read_studio_private_json(args.plan, 262144) if args.plan else
                    propose_dialogue_localization(
                        docs, npc, dialogue, PROMPT, args.locale, authorized=True,
                        expected_source_digest=program.source_digest,
                        expected_initial_session_digest=initial.digest))
            receipt = compile_dialogue_localization(
                docs, npc, dialogue, plan, authorized=True,
                expected_source_digest=program.source_digest,
                expected_initial_session_digest=initial.digest)
        if args.editor_html:
            print(render_dialogue_localization_editor_html(
                docs, npc, dialogue, receipt, authorized=True).decode("utf-8"))
            return 0
        result = {"schema": "skeleton.cli.studio_quest_dialogue_localization.v1",
                  "localization": receipt, "file_write_performed": False,
                  "release_certified": False}
        if args.handoff:
            result["playable_handoff"] = compile_dialogue_localized_handoff(
                docs, npc, dialogue, receipt, authorized=True)
        if args.publish:
            result["publication"] = publish_dialogue_localization(
                docs, npc, dialogue, receipt, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
