"""CLI for source-replayed playable NPC contact eligibility and private custody."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_npc_contact_handoff import (
    compile_npc_contact_handoff, publish_npc_contact_handoff,
    restore_npc_contact_handoff, render_npc_contact_handoff_html,
)
from skeleton.ai.game_builder.studio_waypoint_handoff import (
    MAX_BYTES as MAX_WALK_HANDOFF_BYTES, replay_waypoint_handoff,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify authored NPC contact at a replayed playable position")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--session-json", help="Canonical walk session JSON")
    mode.add_argument("--walk-handoff-json", help="Verified waypoint-to-playable handoff JSON")
    mode.add_argument("--restore", type=Path)
    parser.add_argument("--expected-session", help="Lease for direct session or restore")
    parser.add_argument("--expected-prior-session", help="Prior lease for waypoint handoff")
    parser.add_argument("--npc-id", help="Authored NPC identity")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--html-sha256", action="store_true")
    args = parser.parse_args(argv)
    if args.restore and (args.publish or not args.expected_session):
        parser.error("restore requires session lease and cannot publish")
    if args.session_json and not args.expected_session:
        parser.error("direct walk session requires --expected-session")
    if args.walk_handoff_json and (not args.expected_prior_session
                                   or args.expected_session):
        parser.error("waypoint handoff requires only --expected-prior-session")
    if not args.restore and not args.npc_id:
        parser.error("NPC contact compilation requires --npc-id")
    try:
        documents = read_blueprint(args.project)
        if args.restore:
            receipt = restore_npc_contact_handoff(
                documents, args.restore, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=args.expected_session,
            )
        else:
            if args.walk_handoff_json:
                handoff = _strict(
                    args.walk_handoff_json, max_bytes=MAX_WALK_HANDOFF_BYTES,
                )
                proof = replay_waypoint_handoff(
                    documents, handoff, authorized=True,
                    expected_source_digest=args.expected_source,
                    expected_session_digest=args.expected_prior_session,
                )
                session = proof["post_walk_receipt"]
                expected_session = proof["post_session_digest"]
            else:
                session = _strict(args.session_json, max_bytes=256 * 1024)
                expected_session = args.expected_session
            receipt = compile_npc_contact_handoff(
                documents, session, npc_id=args.npc_id, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=expected_session,
            )
        output: dict[str, object] = {
            "npc_contact": receipt, "file_write_performed": False,
        }
        if args.html_sha256:
            output["html_sha256"] = sha256(render_npc_contact_handoff_html(
                documents, receipt, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=receipt["session_digest"],
            )).hexdigest()
        if args.publish:
            output["publication"] = publish_npc_contact_handoff(
                documents, receipt, args.publish, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=receipt["session_digest"],
            )
            output["file_write_performed"] = True
    except (StudioQuestError, PermissionError, OSError, ValueError, TypeError,
            KeyError, UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
