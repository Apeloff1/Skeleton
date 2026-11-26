"""Offline CLI: typed authored quest replay fault localization and custody."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_npc_knowledge_relay_cli import _private_json
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_replay_diagnostic_editor import (
    render_replay_diagnostic_editor, import_replay_diagnostic_editor_export,
)
from skeleton.ai.game_builder.studio_quest_replay_diagnostic import (
    PROMPT, compile_replay_diagnostic, propose_replay_diagnostic,
    replay_replay_diagnostic, compile_replay_diagnostic_handoff,
    publish_replay_diagnostic, restore_replay_diagnostic,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Diagnose authored quest replay against exact source and session")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-session", required=True)
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--plan-file", type=Path)
    modes.add_argument("--restore", type=Path)
    modes.add_argument("--editor-export", type=Path)
    ap.add_argument("--baseline", type=Path,
                    help="Private previously published diagnostic receipt directory")
    ap.add_argument("--editor-preview", action="store_true")
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--handoff", action="store_true")
    args = ap.parse_args(argv)
    if args.restore and args.publish:
        ap.error("restore cannot publish")
    if args.editor_export and not args.baseline:
        ap.error("editor export requires --baseline")
    if args.editor_preview and (args.publish or args.handoff):
        ap.error("editor preview cannot publish or handoff")
    try:
        documents = read_blueprint(args.project)
        leases = {"authorized": True,
                  "expected_source_digest": args.expected_source,
                  "expected_initial_session_digest": args.expected_session}
        if args.restore:
            report = restore_replay_diagnostic(
                documents, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
            if report["initial_session_digest"] != args.expected_session:
                raise StudioQuestError("stale restored diagnostic session")
        elif args.editor_export:
            baseline = restore_replay_diagnostic(
                documents, args.baseline, authorized=True,
                expected_source_digest=args.expected_source)
            report = import_replay_diagnostic_editor_export(
                documents, baseline, args.editor_export, **leases)
        elif args.prompt:
            report = propose_replay_diagnostic(documents, PROMPT, **leases)
        else:
            report = compile_replay_diagnostic(
                documents, _private_json(args.plan_file, 32768), **leases)
        replay_replay_diagnostic(documents, report, authorized=True)
        if args.editor_preview:
            html, _ = render_replay_diagnostic_editor(
                documents, report, authorized=True)
            print(html.decode("utf-8"))
            return 0
        result: dict[str, object] = {
            "schema": "skeleton.cli.studio_quest_replay_diagnostic.v1",
            "diagnostic": report, "file_write_performed": False,
            "release_certified": False,
        }
        if args.handoff:
            result["playable_handoff"] = compile_replay_diagnostic_handoff(
                documents, report, authorized=True)
        if args.publish:
            result["publication"] = publish_replay_diagnostic(
                documents, report, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
