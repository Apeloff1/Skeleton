"""Operator CLI for fail-closed authored quest readiness and private receipts."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from scripts.studio_npc_knowledge_relay_cli import _private_json
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_readiness_editor import (
    render_quest_readiness_editor, import_quest_readiness_editor_export,
)
from skeleton.ai.game_builder.studio_quest_readiness import (
    PROMPT, compile_quest_readiness, propose_quest_readiness,
    replay_quest_readiness, compile_quest_readiness_handoff,
    publish_quest_readiness, restore_quest_readiness,
    render_quest_readiness_html,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prove original quest ending coverage AND terminal-branch safety")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-session", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--budget-file", type=Path)
    modes.add_argument("--restore", type=Path)
    modes.add_argument("--editor-export", type=Path)
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--playable", action="store_true")
    parser.add_argument("--html-preview", action="store_true")
    parser.add_argument("--editor-preview", action="store_true")
    args = parser.parse_args(argv)
    if args.restore and args.publish:
        parser.error("restore cannot publish")
    if args.html_preview and args.publish:
        parser.error("HTML preview cannot publish")
    if args.editor_preview and (args.publish or args.playable or args.html_preview):
        parser.error("editor preview cannot publish, handoff or combine previews")
    try:
        documents = read_blueprint(args.project)
        options = {
            "authorized": True,
            "expected_source_digest": args.expected_source,
            "expected_initial_session_digest": args.expected_session,
        }
        if args.restore:
            report = restore_quest_readiness(
                documents, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
            if report["initial_session_digest"] != args.expected_session:
                raise StudioQuestError("stale restored readiness initial session")
        elif args.editor_export:
            report = import_quest_readiness_editor_export(
                documents, args.editor_export, **options)
        elif args.prompt:
            report = propose_quest_readiness(documents, PROMPT, **options)
        else:
            report = compile_quest_readiness(
                documents, _private_json(args.budget_file, 32768), **options)
        replay_quest_readiness(documents, report, authorized=True)
        if args.editor_preview:
            html, _ = render_quest_readiness_editor(
                documents, report, authorized=True)
            print(html.decode("utf-8"))
            return 0
        if args.html_preview:
            print(render_quest_readiness_html(
                documents, report, authorized=True).decode("utf-8"))
            return 0
        result: dict[str, object] = {
            "schema": "skeleton.cli.studio_quest_readiness.v1",
            "readiness": report, "file_write_performed": False,
            "release_certified": False,
        }
        if args.playable:
            result["playable_handoff"] = compile_quest_readiness_handoff(
                documents, report, authorized=True)
        if args.publish:
            result["publication"] = publish_quest_readiness(
                documents, report, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
