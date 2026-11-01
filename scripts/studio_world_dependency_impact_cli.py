"""CLI: source-bound impact preview, private publication and exact replay."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_world_dependency_impact import (
    compile_dependency_impact, publish_dependency_impact,
    render_dependency_impact_html, restore_dependency_impact,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Source-leased world dependency edit impact")
    parser.add_argument("--expected-catalog", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--candidate-graph", help="Strict candidate graph JSON")
    modes.add_argument("--restore", type=Path, help="Private impact directory")
    parser.add_argument("--baseline-proof", help="Strict source-replayed baseline proof JSON")
    parser.add_argument("--publish", type=Path, help="Existing private output directory")
    parser.add_argument("--html-sha256", action="store_true")
    args = parser.parse_args(argv)
    if args.candidate_graph and not args.baseline_proof:
        parser.error("candidate impact requires baseline proof")
    if args.restore and (args.baseline_proof or args.publish):
        parser.error("restore cannot mutate or accept an alternate baseline")
    try:
        if args.restore:
            proof = restore_dependency_impact(
                args.restore, authorized=True,
                expected_catalog_digest=args.expected_catalog,
            )
        else:
            proof = compile_dependency_impact(
                _strict(args.baseline_proof, max_bytes=512 * 1024),
                _strict(args.candidate_graph, max_bytes=48 * 1024),
                authorized=True, expected_catalog_digest=args.expected_catalog,
            )
        output: dict[str, object] = {"impact": proof, "file_write_performed": False}
        if args.html_sha256:
            output["html_sha256"] = sha256(
                render_dependency_impact_html(proof, authorized=True)
            ).hexdigest()
        if args.publish:
            output["publication"] = publish_dependency_impact(
                proof, args.publish, authorized=True,
            )
            output["file_write_performed"] = True
    except (StudioQuestError, OSError, PermissionError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
