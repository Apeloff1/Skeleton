"""Operator CLI for original scene asset recipe bindings and handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint, compile_preview
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_asset_bindings import (
    compile_scene_asset_bindings, publish_scene_asset_bindings,
    verify_scene_asset_bindings,
)
from scripts.studio_scene_schedule_cli import _strict


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Original scene asset work order compilation")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-visual", required=True)
    ap.add_argument("--expected-session")
    ap.add_argument("--actions", default="[]")
    ap.add_argument("--assignments", help="Strict JSON scene/asset-to-recipe assignments")
    ap.add_argument("--compile-preview", action="store_true",
                    help="Also compile existing 2D HTML5 game preview; no native asset binding claim")
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--publish-directory", type=Path)
    modes.add_argument("--verify-directory", type=Path)
    args = ap.parse_args(argv)
    if args.verify_directory and args.assignments is not None:
        ap.error("--verify-directory reads saved assignments; omit --assignments")
    if not args.verify_directory and args.assignments is None:
        ap.error("scene asset authoring requires --assignments")
    try:
        actions = _strict(args.actions, max_bytes=16384)
        docs = read_blueprint(args.project)
        if args.verify_directory:
            result = verify_scene_asset_bindings(
                docs, actions, args.verify_directory, authorized=True,
                expected_source_digest=args.expected_source,
                expected_visual_digest=args.expected_visual)
        else:
            assignments = _strict(args.assignments, max_bytes=32768)
            result = compile_scene_asset_bindings(
                docs, actions, assignments, authorized=True,
                expected_source_digest=args.expected_source,
                expected_visual_digest=args.expected_visual,
                expected_session_digest=args.expected_session)
            if args.publish_directory:
                published = publish_scene_asset_bindings(
                    result, args.publish_directory, authorized=True)
                result = {"binding": result, "publication": published}
        if args.compile_preview:
            preview = compile_preview(args.project, authorized=True)
            result = {"asset_plan": result, "canonical_html5_preview_receipt": preview.receipt(),
                      "native_asset_binding_in_preview_verified": False,
                      "native_genre_runtime_verified": False,
                      "release_certified": False}
    except (StudioQuestError, PermissionError, ValueError, TypeError,
            OSError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
