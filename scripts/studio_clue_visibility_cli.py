"""Offline CLI for source-bound clue planning, edit, replay and HTML5 handoff."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_clue_visibility import (
    compile_clue_visibility, propose_clue_visibility, compile_clue_playable,
    publish_clue_visibility, restore_clue_visibility, publish_clue_playable,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Original clue visibility compiler")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-session")
    ap.add_argument("--actions", default="[]")
    ap.add_argument("--prompt")
    ap.add_argument("--authoring")
    ap.add_argument("--import-authoring", type=Path)
    ap.add_argument("--baseline-authoring")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--restore", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--handoff-manifest", action="store_true")
    ap.add_argument("--publish-playable", type=Path)
    args = ap.parse_args(argv)
    if sum(x is not None for x in (args.prompt, args.authoring, args.import_authoring, args.restore)) != 1:
        ap.error("choose exactly one prompt, authoring or restore")
    if args.restore and args.publish:
        ap.error("cannot overwrite a restored receipt")
    try:
        docs = read_blueprint(args.project)
        actions = _strict(args.actions, max_bytes=16384)
        if type(actions) is not list:
            raise StudioQuestError("clue actions must be list")
        if args.restore:
            report = restore_clue_visibility(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=args.expected_session)
            result = {"clues": report}
        elif args.prompt:
            proposal = propose_clue_visibility(
                docs, actions, args.prompt, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=args.expected_session)
            report = proposal["detail"]
            result = {"proposal": proposal, "clues": report}
        else:
            if args.import_authoring:
                from skeleton.ai.game_builder.studio_ecosystem_clue_editor import (
                    load_clue_editor_export,
                )
                if args.baseline_authoring is None:
                    raise StudioQuestError("import requires exact baseline authoring")
                baseline = _strict(args.baseline_authoring, max_bytes=32768)
                original = compile_clue_visibility(
                    docs, actions, baseline, authorized=True,
                    expected_source_digest=args.expected_source,
                    expected_session_digest=args.expected_session)
                authoring = load_clue_editor_export(
                    args.import_authoring, authorized=True,
                    expected_project_id=original["project_id"],
                    expected_source_digest=original["source_digest"],
                    expected_session_digest=original["session_digest"],
                    expected_baseline_digest=original["clue_digest"])
            else:
                authoring = _strict(args.authoring, max_bytes=32768)
            report = compile_clue_visibility(
                docs, actions, authoring, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=args.expected_session)
            result = {"clues": report}
        if args.editor_directory:
            from skeleton.ai.game_builder.studio_ecosystem_clue_editor import (
                publish_clue_editor,
            )
            result["editor"] = publish_clue_editor(
                docs, report, args.editor_directory, authorized=True)
        if args.publish:
            result["publication"] = publish_clue_visibility(
                docs, report, args.publish, authorized=True)
        if args.handoff_manifest or args.publish_playable:
            manifest, _bundle = compile_clue_playable(docs, report, authorized=True)
            result["playable_handoff"] = manifest
        if args.publish_playable:
            result["playable_publication"] = publish_clue_playable(
                docs, report, args.publish_playable, authorized=True)
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
