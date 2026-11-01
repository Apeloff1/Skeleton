"""Operator CLI for integrated original offline director game handoffs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_director_handoff import (
    compile_director_handoff, publish_director_handoff, verify_director_handoff,
)
from scripts.studio_scene_schedule_cli import _strict


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compile original HTML5 director handoff")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-visual", required=True)
    ap.add_argument("--expected-session")
    ap.add_argument("--actions", default="[]")
    ap.add_argument("--schedule", required=True)
    ap.add_argument("--assignments", required=True)
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--publish-directory", type=Path)
    modes.add_argument("--verify-directory", type=Path)
    args = ap.parse_args(argv)
    try:
        actions = _strict(args.actions, max_bytes=16384)
        schedule = _strict(args.schedule, max_bytes=16384)
        assignments = _strict(args.assignments, max_bytes=32768)
        docs = read_blueprint(args.project)
        kwargs = dict(
            authorized=True, expected_source_digest=args.expected_source,
            expected_visual_digest=args.expected_visual,
            expected_session_digest=args.expected_session)
        if args.verify_directory:
            manifest = verify_director_handoff(
                docs, actions, schedule, assignments, args.verify_directory, **kwargs)
        else:
            manifest, bundle = compile_director_handoff(
                docs, actions, schedule, assignments, **kwargs)
            if args.publish_directory:
                published = publish_director_handoff(
                    manifest, bundle, args.publish_directory, authorized=True,
                    documents=docs, actions=actions,
                    schedule=schedule, assignments=assignments)
                manifest = {"manifest": manifest, "publication": published}
    except (StudioQuestError, PermissionError, ValueError, TypeError,
            OSError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
