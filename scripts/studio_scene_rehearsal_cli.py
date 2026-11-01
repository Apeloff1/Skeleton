"""Operator CLI for original source-leased scene timing what-if and playable."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_rehearsal import (
    compile_scene_rehearsal, compile_rehearsed_playable,
    publish_scene_rehearsal, verify_scene_rehearsal,
)
from skeleton.ai.game_builder.studio_ecosystem_director_handoff import (
    publish_director_handoff,
)
from scripts.studio_scene_schedule_cli import _strict


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Canonical scene timing what-if")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-session")
    ap.add_argument("--actions", default="[]")
    ap.add_argument("--baseline")
    ap.add_argument("--candidate")
    ap.add_argument("--publish-directory", type=Path)
    ap.add_argument("--verify-directory", type=Path)
    ap.add_argument("--playable-assignments")
    ap.add_argument("--visual-digest")
    ap.add_argument("--publish-playable-directory", type=Path)
    args = ap.parse_args(argv)
    if args.verify_directory and (args.baseline or args.candidate or args.publish_directory):
        ap.error("restore reads persisted schedule, not new authoring")
    if not args.verify_directory and (args.baseline is None or args.candidate is None):
        ap.error("rehearsal requires --baseline and --candidate")
    if bool(args.playable_assignments is not None) != bool(args.visual_digest is not None):
        ap.error("playable assignments and visual digest must be paired")
    if args.publish_playable_directory and (
            args.playable_assignments is None or args.verify_directory):
        ap.error("playable publication requires current authored schedules")
    try:
        actions = _strict(args.actions, max_bytes=16384)
        if type(actions) is not list:
            raise StudioQuestError("rehearsal actions must be list")
        docs = read_blueprint(args.project)
        if args.verify_directory:
            report = verify_scene_rehearsal(
                docs, actions, args.verify_directory, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=args.expected_session)
        else:
            report = compile_scene_rehearsal(
                docs, actions, _strict(args.baseline, max_bytes=16384),
                _strict(args.candidate, max_bytes=16384), authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=args.expected_session)
        result: dict[str, object] = {"rehearsal": report}
        if args.playable_assignments is not None:
            assignments = _strict(args.playable_assignments, max_bytes=32768)
            manifest, bundle = compile_rehearsed_playable(
                docs, actions, report, assignments, authorized=True,
                expected_visual_digest=args.visual_digest)
            result["playable"] = {
                "bundle_sha256": manifest["bundle_sha256"],
                "bundle_bytes": manifest["bundle_bytes"],
                "scene_schedule_digest": manifest["scene_schedule_digest"],
                "canonical_html5_gameplay_replay_verified": True,
                "native_timing_verified": False, "release_certified": False}
            if args.publish_playable_directory:
                result["playable_publication"] = publish_director_handoff(
                    manifest, bundle, args.publish_playable_directory,
                    authorized=True, documents=docs, actions=actions,
                    schedule=report["candidate_schedule"], assignments=assignments)
        if args.publish_directory:
            result["publication"] = publish_scene_rehearsal(
                report, args.publish_directory, authorized=True,
                documents=docs, actions=actions)
    except (StudioQuestError, PermissionError, OSError, ValueError, TypeError,
            UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
