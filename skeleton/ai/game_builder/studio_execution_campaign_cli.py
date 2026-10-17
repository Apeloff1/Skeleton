"""Execute an explicit multi-console Jeeves original-game studio E2E pass.

Full qualification reports only real artifact-bound results. Each optional
runtime must be independently installed, authorized, executed and verified.
Generated game canvas capture requires separate affirmative consent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .studio_campaign_cli import parse_campaign_order_file
from .studio_execution_campaign import (
    ExecutionPolicy, STAGES, run_studio_execution_campaign,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument(
        "--stages", default="source,rom,emulator,browser,godot",
        help="ordered comma-delimited stages: " + ",".join(STAGES),
    )
    parser.add_argument("--authorize-local-operation", action="store_true")
    parser.add_argument("--execute-run", action="store_true")
    parser.add_argument("--consent-generated-game-canvas", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--max-emulator-frames", type=int, default=260000)
    parser.add_argument("--max-source-targets", type=int)
    parser.add_argument("--stop-after-blocker", action="store_true")
    args = parser.parse_args(argv)
    if not args.authorize_local_operation or not args.execute_run:
        parser.error("E2E production requires explicit local authority and execution opt-in")
    try:
        order = parse_campaign_order_file(args.order)
        policy = ExecutionPolicy(
            stages=tuple(args.stages.split(",")),
            timeout_seconds=args.timeout_seconds,
            max_emulator_frames=args.max_emulator_frames,
            max_sources_per_run=args.max_source_targets,
            stop_after_blocker=args.stop_after_blocker,
            capture_consent=args.consent_generated_game_canvas,
        )
        result = run_studio_execution_campaign(
            order, args.campaign, policy=policy, authorized=True, execute=True,
        )
    except (OSError, ValueError, RuntimeError, PermissionError) as exc:
        print(json.dumps({"success": False, "error": type(exc).__name__},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if (
        not result["blocked_stage_attempts"]
        and not result["unsupported_stage_attempts"]
        and result["verified_stage_attempts"] == result["total_stage_attempts"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
