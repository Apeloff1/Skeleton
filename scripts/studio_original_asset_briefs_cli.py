"""Offline original asset production brief authoring and compilation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_original_asset_briefs import (
    PROMPT, compile_original_asset_briefs, propose_original_asset_briefs,
    replay_original_asset_briefs, publish_original_asset_briefs,
    restore_original_asset_briefs, render_original_asset_briefs_html,
    compile_original_asset_briefs_playable,
)
from skeleton.ai.game_builder.studio_original_asset_briefs_editor import (
    publish_original_asset_briefs_editor, load_original_asset_briefs_editor_export,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Original source-bound asset briefs")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-visual", required=True)
    ap.add_argument("--actions")
    ap.add_argument("--bindings")
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--authoring")
    modes.add_argument("--import-authoring", type=Path)
    modes.add_argument("--restore", type=Path)
    ap.add_argument("--baseline-briefs")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--html-sha256", action="store_true")
    ap.add_argument("--playable-manifest", action="store_true")
    args = ap.parse_args(argv)
    if args.restore and (args.actions or args.bindings or args.baseline_briefs):
        ap.error("restore cannot combine with authoring")
    if not args.restore and (args.actions is None or args.bindings is None):
        ap.error("asset briefs require actions and binding receipt")
    if args.import_authoring and not args.baseline_briefs:
        ap.error("editor import requires baseline asset briefs")
    try:
        docs = read_blueprint(args.project)
        if args.restore:
            detail = restore_original_asset_briefs(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
            if detail["visual_digest"] != args.expected_visual:
                raise StudioQuestError("stale original asset visual lease")
        else:
            actions = _strict(args.actions, max_bytes=16384)
            bindings = _strict(args.bindings, max_bytes=262144)
            if args.prompt:
                detail = propose_original_asset_briefs(
                    docs, actions, bindings, PROMPT, authorized=True,
                    expected_source_digest=args.expected_source,
                    expected_visual_digest=args.expected_visual)
            else:
                expected_session = None
                if args.import_authoring:
                    prior = replay_original_asset_briefs(
                        docs, _strict(args.baseline_briefs, max_bytes=524288),
                        authorized=True)
                    if (prior["binding_digest"] != bindings.get("asset_binding_digest")
                            or prior["actions"] != actions):
                        raise StudioQuestError("stale original asset editor binding/session")
                    expected_session = prior["session_digest"]
                    authoring = load_original_asset_briefs_editor_export(
                        args.import_authoring, authorized=True,
                        expected_project_id=prior["project_id"],
                        expected_source_digest=prior["source_digest"],
                        expected_visual_digest=prior["visual_digest"],
                        expected_session_digest=prior["session_digest"],
                        expected_baseline_digest=prior["asset_brief_digest"])
                else:
                    authoring = _strict(args.authoring, max_bytes=131072)
                detail = compile_original_asset_briefs(
                    docs, actions, bindings, authoring, authorized=True,
                    expected_source_digest=args.expected_source,
                    expected_visual_digest=args.expected_visual,
                    expected_session_digest=expected_session)
        result: dict[str, object] = {"asset_briefs": detail, "file_write_performed": False}
        if args.html_sha256:
            from hashlib import sha256
            result["html_sha256"] = sha256(render_original_asset_briefs_html(
                docs, detail, authorized=True)).hexdigest()
        if args.playable_manifest:
            result["playable_handoff"] = compile_original_asset_briefs_playable(
                docs, detail, authorized=True)
        if args.editor_directory:
            result["editor"] = publish_original_asset_briefs_editor(
                docs, detail, args.editor_directory, authorized=True)
        if args.publish:
            result["publication"] = publish_original_asset_briefs(
                docs, detail, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (StudioQuestError, OSError, ValueError, TypeError) as exc:
        ap.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
