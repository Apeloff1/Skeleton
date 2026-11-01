"""Operator CLI: prompt, edit, replay, private custody and playable handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_temporal_windows import (
    compile_temporal_windows, propose_temporal_windows,
    publish_temporal_windows, restore_temporal_windows, compile_temporal_playable,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-bound temporal world compiler")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-session")
    ap.add_argument("--actions", default="[]")
    ap.add_argument("--prompt")
    ap.add_argument("--authoring")
    ap.add_argument("--restore", type=Path)
    ap.add_argument("--import-authoring", type=Path)
    ap.add_argument("--baseline-authoring")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--handoff-manifest", action="store_true")
    args = ap.parse_args(argv)
    if sum(value is not None for value in (args.prompt, args.authoring, args.import_authoring, args.restore)) != 1:
        ap.error("choose exactly one prompt, authoring or restore")
    try:
        docs = read_blueprint(args.project)
        actions = _strict(args.actions, max_bytes=16384)
        if type(actions) is not list:
            raise StudioQuestError("temporal actions must be a list")
        if args.restore:
            if args.publish:
                raise StudioQuestError("cannot overwrite a restored temporal receipt")
            receipt = restore_temporal_windows(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
            if args.expected_session and receipt["session_digest"] != args.expected_session:
                raise StudioQuestError("stale restored temporal session")
            result = {"temporal": receipt}
        elif args.prompt:
            proposal = propose_temporal_windows(
                docs, actions, args.prompt, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=args.expected_session)
            receipt = proposal["detail"]
            result = {"proposal": proposal, "temporal": receipt}
        else:
            if args.import_authoring:
                from skeleton.ai.game_builder.studio_ecosystem_temporal_editor import (
                    load_temporal_editor_export,
                )
                if args.baseline_authoring is None:
                    raise StudioQuestError("temporal import requires baseline authoring")
                baseline = _strict(args.baseline_authoring, max_bytes=32768)
                original = compile_temporal_windows(
                    docs, actions, baseline, authorized=True,
                    expected_source_digest=args.expected_source,
                    expected_session_digest=args.expected_session)
                authoring = load_temporal_editor_export(
                    args.import_authoring, authorized=True,
                    expected_project_id=original["project_id"],
                    expected_source_digest=original["source_digest"],
                    expected_session_digest=original["session_digest"],
                    expected_baseline_digest=original["temporal_digest"])
            else:
                authoring = _strict(args.authoring, max_bytes=32768)
            receipt = compile_temporal_windows(
                docs, actions, authoring, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=args.expected_session)
            result = {"temporal": receipt}
        if args.editor_directory:
            from skeleton.ai.game_builder.studio_ecosystem_temporal_editor import (
                publish_temporal_editor,
            )
            result["editor"] = publish_temporal_editor(
                docs, receipt, args.editor_directory, authorized=True)
        if args.publish:
            result["publication"] = publish_temporal_windows(
                docs, receipt, args.publish, authorized=True)
        if args.handoff_manifest:
            result["playable_handoff"], _ = compile_temporal_playable(
                docs, receipt, authorized=True)
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
