"""Operator CLI: prompt -> typed NPC knowledge -> private edit -> replay proof."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge import (
    compile_npc_knowledge, publish_npc_knowledge, render_npc_knowledge_html,
    verify_npc_knowledge,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_prompt import propose_npc_knowledge
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_editor import (
    load_npc_knowledge_editor_export, render_npc_knowledge_editor,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import replay_quest
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_compare import compare_npc_knowledge
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from scripts.studio_scene_schedule_cli import _strict


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-bound NPC knowledge director handoff")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-session")
    ap.add_argument("--actions", default="[]")
    inputs = ap.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--prompt", help="Source-derived deterministic knowledge plan")
    inputs.add_argument("--authoring-json", help="Strict JSON knowledge reveal edits")
    inputs.add_argument("--editor-export", type=Path,
                        help="Private source/session-leased JSON from offline knowledge editor")
    outputs = ap.add_mutually_exclusive_group()
    outputs.add_argument("--publish-directory", type=Path)
    outputs.add_argument("--verify-directory", type=Path)
    ap.add_argument("--compare-actions", help="Second canonical quest history for knowledge branch impact")
    ap.add_argument("--include-editor-html", action="store_true",
                    help="Include offline source-bound editable HTML form")
    ap.add_argument("--include-html", action="store_true",
                    help="Include escaped script-free director companion HTML in output")
    args = ap.parse_args(argv)
    try:
        docs = read_blueprint(args.project)
        actions = _strict(args.actions, max_bytes=16384)
        kwargs = {
            "authorized": True,
            "expected_source_digest": args.expected_source,
            "expected_session_digest": args.expected_session,
        }
        proposal = (propose_npc_knowledge(docs, actions, args.prompt, **kwargs)
                    if args.prompt is not None else None)
        authoring = (proposal["authoring"] if proposal is not None else
                     load_npc_knowledge_editor_export(
                         args.editor_export, authorized=True,
                         expected_project_id=args.project,
                         expected_source_digest=args.expected_source,
                         expected_session_digest=replay_quest(
                             docs, actions, authorized=True).digest)
                     if args.editor_export is not None else
                     _strict(args.authoring_json, max_bytes=65536))
        if args.verify_directory is not None:
            compiled = verify_npc_knowledge(
                docs, actions, args.verify_directory, authorized=True,
                expected_source_digest=args.expected_source)
            if compiled["authoring"] != authoring:
                raise StudioQuestError("published NPC knowledge authoring differs from request")
            if args.expected_session is not None and (
                    compiled["session_digest"] != args.expected_session):
                raise StudioQuestError("stale published NPC knowledge session")
        else:
            compiled = compile_npc_knowledge(docs, actions, authoring, **kwargs)
        output: dict[str, object] = {"compiled": compiled}
        if proposal is not None:
            output["proposal"] = proposal
        if args.compare_actions is not None:
            other_actions = _strict(args.compare_actions, max_bytes=16384)
            output["comparison"] = compare_npc_knowledge(
                docs, actions, other_actions, authoring, authorized=True,
                expected_source_digest=args.expected_source,
                expected_before_session=args.expected_session)
        if args.publish_directory is not None:
            output["publication"] = publish_npc_knowledge(
                compiled, args.publish_directory, authorized=True,
                documents=docs, actions=actions)
        if args.include_editor_html:
            editor, editor_receipt = render_npc_knowledge_editor(
                docs, actions, compiled, authorized=True)
            output["editor_html"] = editor.decode("utf-8")
            output["editor_receipt"] = editor_receipt
        if args.include_html:
            output["director_companion_html"] = render_npc_knowledge_html(
                compiled).decode("utf-8")
    except (StudioQuestError, ValueError, TypeError, OSError,
            UnicodeError, PermissionError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
