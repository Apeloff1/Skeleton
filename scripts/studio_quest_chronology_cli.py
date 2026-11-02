"""CLI for source-leased authored quest chronology and deterministic replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_chronology import (
    PROMPT, propose_quest_chronology, compile_quest_chronology,
    render_quest_chronology_editor, render_quest_chronology_preview,
    publish_quest_chronology, restore_quest_chronology,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review original quest time windows")
    parser.add_argument("--project", required=True)
    parser.add_argument("--actions-file", type=Path)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--editor-html", action="store_true")
    parser.add_argument("--preview-html", action="store_true")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args(argv)
    if args.publish and args.restore:
        parser.error("cannot publish and restore together")
    if args.editor_html and (args.publish or args.restore or args.preview_html):
        parser.error("editor is read-only")
    if args.preview_html and (args.publish or args.restore):
        parser.error("preview is read-only")
    try:
        documents = read_blueprint(args.project)
        program = compile_quest_program(documents)
        initial = start_quest(documents, authorized=True)
        if args.restore:
            receipt = restore_quest_chronology(
                documents, args.restore, authorized=True)
        else:
            if args.plan_file:
                plan = read_studio_private_json(args.plan_file, 128 * 1024)
            else:
                if args.actions_file is None:
                    parser.error("--actions-file required to propose chronology")
                actions = read_studio_private_json(
                    args.actions_file, 128 * 1024).get("actions")
                plan = propose_quest_chronology(
                    documents, PROMPT, actions, authorized=True,
                    expected_source_digest=program.source_digest,
                    expected_initial_session_digest=initial.digest)
            if args.editor_html:
                print(render_quest_chronology_editor(
                    documents, plan, authorized=True).decode("utf-8"))
                return 0
            if not args.plan_file:
                if args.publish or args.preview_html:
                    parser.error("reviewed --plan-file required")
                print(json.dumps({"schema": "skeleton.cli.quest_chronology_proposal.v1",
                                  "plan": plan}, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False))
                return 0
            receipt = compile_quest_chronology(
                documents, plan, authorized=True,
                expected_source_digest=program.source_digest,
                expected_initial_session_digest=initial.digest)
        if args.preview_html:
            print(render_quest_chronology_preview(
                documents, receipt, authorized=True).decode("utf-8"))
            return 0
        result = {"schema": "skeleton.cli.quest_chronology.v1",
                  "chronology": receipt, "file_write_performed": False}
        if args.publish:
            result["publication"] = publish_quest_chronology(
                documents, receipt, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
