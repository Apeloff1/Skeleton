"""CLI for source-verified hazard-aware authored waypoint itineraries."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_waypoint_risk import (
    compile_waypoint_risk, publish_waypoint_risk, render_waypoint_risk_html,
    restore_waypoint_risk,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Original-world risk-aware waypoint route")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--waypoints", help="JSON authored waypoint coordinates")
    mode.add_argument("--restore", type=Path)
    parser.add_argument("--scene-index", type=int, default=0)
    parser.add_argument("--start", default="[1,1]")
    parser.add_argument("--max-hazard-contacts", type=int, default=0)
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--html-sha256", action="store_true")
    args = parser.parse_args(argv)
    if args.restore and args.publish:
        parser.error("restore cannot publish")
    try:
        documents = read_blueprint(args.project)
        if args.restore:
            receipt = restore_waypoint_risk(
                documents, args.restore, authorized=True,
                expected_source_digest=args.expected_source,
            )
        else:
            receipt = compile_waypoint_risk(
                documents, scene_index=args.scene_index,
                start=_strict(args.start, max_bytes=4096),
                waypoints=_strict(args.waypoints, max_bytes=4096),
                max_hazard_contacts=args.max_hazard_contacts,
                authorized=True, expected_source_digest=args.expected_source,
            )
        output: dict[str, object] = {
            "risk_route": receipt, "file_write_performed": False,
        }
        if args.html_sha256:
            output["html_sha256"] = sha256(render_waypoint_risk_html(
                documents, receipt, authorized=True,
                expected_source_digest=args.expected_source,
            )).hexdigest()
        if args.publish:
            output["publication"] = publish_waypoint_risk(
                documents, receipt, args.publish, authorized=True,
                expected_source_digest=args.expected_source,
            )
            output["file_write_performed"] = True
    except (StudioQuestError, OSError, PermissionError, ValueError, TypeError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
