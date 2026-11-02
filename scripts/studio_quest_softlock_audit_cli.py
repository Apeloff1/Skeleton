"""CLI for bounded, source-replayed authored quest softlock audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_npc_knowledge_relay_cli import _private_json
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError,
)
from skeleton.ai.game_builder.studio_quest_softlock_audit import (
    PROMPT, compile_quest_softlock_audit,
    propose_quest_softlock_audit, replay_quest_softlock_audit,
    publish_quest_softlock_audit, restore_quest_softlock_audit,
    render_quest_softlock_html, compile_quest_softlock_handoff,
)
from skeleton.ai.game_builder.studio_quest_softlock_editor import (
    publish_quest_softlock_editor, load_quest_softlock_editor_export,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Original authored quest softlock audit")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-session", required=True)
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--authoring-file", type=Path)
    modes.add_argument("--restore", type=Path)
    modes.add_argument("--editor-export-file", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--baseline-audit-file", type=Path)
    ap.add_argument("--render-editor", type=Path)
    ap.add_argument("--html-preview", action="store_true")
    ap.add_argument("--playable", action="store_true")
    args = ap.parse_args(argv)
    if args.restore and args.publish:
        ap.error("restore cannot publish")
    if bool(args.editor_export_file) != bool(args.baseline_audit_file):
        ap.error("editor import requires a matching baseline audit file")
    if args.html_preview and args.publish:
        ap.error("HTML preview cannot publish")
    try:
        docs = read_blueprint(args.project)
        kwargs = {"authorized": True,
                  "expected_source_digest": args.expected_source,
                  "expected_initial_session_digest": args.expected_session}
        if args.restore:
            result = restore_quest_softlock_audit(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
            if result["initial_session_digest"] != args.expected_session:
                raise StudioQuestError("stale restored softlock session")
        elif args.editor_export_file:
            baseline = _private_json(args.baseline_audit_file, 512 * 1024)
            authoring = load_quest_softlock_editor_export(
                docs, baseline, args.editor_export_file, **kwargs)
            result = compile_quest_softlock_audit(docs, authoring, **kwargs)
        elif args.prompt:
            result = propose_quest_softlock_audit(docs, PROMPT, **kwargs)
        else:
            plan = _private_json(args.authoring_file, 32768)
            result = compile_quest_softlock_audit(docs, plan, **kwargs)
        replay_quest_softlock_audit(docs, result, authorized=True)
        if args.html_preview:
            print(render_quest_softlock_html(
                docs, result, authorized=True).decode("utf-8"))
            return 0
        output: dict[str, object] = {
            "schema": "skeleton.cli.studio_quest_softlock_audit.v1",
            "audit": result, "file_write_performed": False,
            "release_certified": False,
        }
        if args.playable:
            output["playable_handoff"] = compile_quest_softlock_handoff(
                docs, result, authorized=True)
        if args.render_editor:
            output["editor"] = publish_quest_softlock_editor(
                docs, result, args.render_editor, authorized=True)
            output["file_write_performed"] = True
        if args.publish:
            output["publication"] = publish_quest_softlock_audit(
                docs, result, args.publish, authorized=True)
            output["file_write_performed"] = True
        print(json.dumps(output, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
