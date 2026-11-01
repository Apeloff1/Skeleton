"""Operator CLI for integrated original offline director game handoffs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_director_authoring import load_director_authoring
from skeleton.ai.game_builder.studio_ecosystem_director_choice_rehearsal import (
    load_choice_export, replay_choice_export,
)

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
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
    ap.add_argument("--choice-export", type=Path,
                    help="Verify source-leased offline quest choices before playable compilation")
    ap.add_argument("--schedule", help="Strict inline schedule JSON (requires --assignments)")
    ap.add_argument("--assignments", help="Strict inline assignments JSON (requires --schedule)")
    ap.add_argument("--editor-export", type=Path,
                    help="Import the single source-bound JSON exported by director_editor.html")
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--publish-directory", type=Path)
    modes.add_argument("--verify-directory", type=Path)
    args = ap.parse_args(argv)
    if args.editor_export is not None:
        if args.schedule is not None or args.assignments is not None:
            ap.error("--editor-export cannot be combined with inline authoring")
    elif args.schedule is None or args.assignments is None:
        ap.error("provide --editor-export or both --schedule and --assignments")
    try:
        docs = read_blueprint(args.project)
        if args.choice_export is not None:
            if args.actions != "[]" or args.expected_session is None:
                ap.error("--choice-export requires --expected-session and no inline --actions")
            proposal = load_choice_export(args.choice_export)
            verified_choice = replay_choice_export(
                docs, proposal, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=args.expected_session)
            actions = verified_choice["verified_actions"]
            session_lease = verified_choice["result_session_digest"]
        else:
            actions = _strict(args.actions, max_bytes=16384)
            session_lease = args.expected_session
        # A browser export must always be bound to the *current* replay,
        # including when the operator omits --expected-session. A stale
        # exported session may never be silently reinterpreted as a new one.
        if args.editor_export is not None:
            current_session = replay_quest(docs, actions, authorized=True).digest
            if session_lease is not None and session_lease != current_session:
                raise StudioQuestError("stale director editor replay session")
            session_lease = current_session
            schedule, assignments = load_director_authoring(
                args.editor_export, authorized=True,
                expected_source_digest=args.expected_source,
                expected_visual_digest=args.expected_visual,
                expected_session_digest=session_lease)
        else:
            schedule = _strict(args.schedule, max_bytes=16384)
            assignments = _strict(args.assignments, max_bytes=32768)
        kwargs = dict(
            authorized=True, expected_source_digest=args.expected_source,
            expected_visual_digest=args.expected_visual,
            expected_session_digest=session_lease)
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
