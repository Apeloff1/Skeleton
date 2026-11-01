"""CLI for source-bound playable waypoint execution and private handoff saves."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_waypoint_handoff import (
    MAX_BYTES, compile_waypoint_handoff, new_walk_receipt,
    publish_waypoint_handoff, render_waypoint_handoff_html,
    restore_waypoint_handoff,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute authored risk-aware waypoint movement into verified playable save")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--new-session", action="store_true")
    mode.add_argument("--session-json", help="Canonical walk receipt JSON")
    mode.add_argument("--restore", type=Path)
    parser.add_argument("--expected-session", help="SHA-256 lease for existing session")
    parser.add_argument("--waypoints", default="[]")
    parser.add_argument("--max-hazard-contacts", type=int, default=0)
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--html-sha256", action="store_true")
    args = parser.parse_args(argv)
    if args.restore and (args.publish or not args.expected_session):
        parser.error("restore requires --expected-session and cannot publish")
    if args.session_json and not args.expected_session:
        parser.error("existing session requires --expected-session")
    if args.new_session and args.expected_session:
        parser.error("new session digest is computed, not operator supplied")
    try:
        documents = read_blueprint(args.project)
        if args.restore:
            receipt = restore_waypoint_handoff(
                documents, args.restore, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=args.expected_session,
            )
        else:
            session = (
                new_walk_receipt(documents, authorized=True,
                                 expected_source_digest=args.expected_source)
                if args.new_session else _strict(args.session_json, max_bytes=MAX_BYTES)
            )
            receipt = compile_waypoint_handoff(
                documents, session, waypoints=_strict(args.waypoints, max_bytes=4096),
                max_hazard_contacts=args.max_hazard_contacts, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=(
                    session["session_digest"] if args.new_session
                    else args.expected_session),
            )
        output: dict[str, object] = {
            "handoff": receipt, "file_write_performed": False,
        }
        if args.html_sha256:
            output["html_sha256"] = sha256(render_waypoint_handoff_html(
                documents, receipt, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=receipt["prior_session_digest"],
            )).hexdigest()
        if args.publish:
            output["publication"] = publish_waypoint_handoff(
                documents, receipt, args.publish, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=receipt["prior_session_digest"],
            )
            output["file_write_performed"] = True
    except (StudioQuestError, OSError, PermissionError, ValueError, TypeError,
            KeyError, UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
