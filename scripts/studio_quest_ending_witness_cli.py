"""CLI for canonical quest-ending witness search and private replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from skeleton.ai.game_builder.studio_quest_ending_witness import (
    compile_ending_witness, publish_ending_witness, restore_ending_witness,
    render_ending_witness_html,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-bound authored quest ending witness")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source")
    ap.add_argument("--expected-session")
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--target-ending")
    modes.add_argument("--inspect", action="store_true")
    modes.add_argument("--restore", type=Path)
    ap.add_argument("--initial-actions", default="[]")
    ap.add_argument("--max-states", type=int, default=512)
    ap.add_argument("--max-depth", type=int, default=16)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--html-preview", action="store_true")
    args = ap.parse_args(argv)
    if args.inspect and (args.publish or args.html_preview):
        ap.error("source inspection is read-only")
    if not args.inspect and (not args.expected_source or not args.expected_session):
        ap.error("compile/restore requires both exact source and session leases")
    if args.restore and (args.publish or args.initial_actions != "[]"):
        ap.error("restore is read-only and cannot change authored prefix")
    if args.publish and args.html_preview:
        ap.error("HTML preview cannot publish")
    kwargs = {
        "authorized": True, "expected_source_digest": args.expected_source,
        "expected_initial_session_digest": args.expected_session,
    }
    try:
        docs = read_blueprint(args.project)
        if args.inspect:
            actions = _strict(args.initial_actions, max_bytes=16384)
            program = compile_quest_program(docs)
            session = replay_quest(docs, actions, authorized=True)
            print(json.dumps({
                "schema": "skeleton.game_builder.studio_quest_ending_inspection.v1",
                "project_id": program.project_id,
                "source_digest": program.source_digest,
                "session_digest": session.digest,
                "ending_ids": [key for key, _ in program.endings],
                "stage_count": len(program.stages),
                "file_write_performed": False, "release_certified": False,
            }, sort_keys=True, separators=(",", ":"), allow_nan=False))
            return 0
        if args.restore:
            result = restore_ending_witness(docs, args.restore, **kwargs)
        else:
            actions = _strict(args.initial_actions, max_bytes=16384)
            result = compile_ending_witness(
                docs, target_ending=args.target_ending,
                initial_actions=actions, max_states=args.max_states,
                max_depth=args.max_depth, **kwargs)
        if args.html_preview:
            print(render_ending_witness_html(docs, result, **kwargs).decode("utf-8"))
            return 0
        output = {"witness": result, "file_write_performed": False}
        if args.publish:
            output["publication"] = publish_ending_witness(
                docs, result, args.publish, **kwargs)
            output["file_write_performed"] = True
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, KeyError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
