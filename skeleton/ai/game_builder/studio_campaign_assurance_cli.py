"""Inspect complete Jeeves production gates and explicitly qualify native ROMs.

Inspection is read-only, including Dragon evidence. Compile mode requires both
operator authorization and the separate --execute-build flag; never starts
automatically or grants the Jeeves model an arbitrary process executor.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .studio_campaign_cli import parse_campaign_order_file
from .studio_campaign_assurance import (
    inspect_production_assurance, qualify_campaign_target, qualify_campaign_browser,
    qualify_campaign_godot,
)
from .studio_e2e_observation import observe_production_campaign
from .studio_pixel_parity import inspect_cross_engine_pixels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--inspect", action="store_true")
    command.add_argument("--dragon-observe", action="store_true")
    command.add_argument("--target", help="specific canonical console ROM target to compile")
    command.add_argument("--browser-target", help="execute native generated HTML5 JavaScript winning replay")
    command.add_argument("--godot-target", help="execute canonical headless Godot 4 winning replay")
    command.add_argument("--pixel-parity-target", help="inspect exact original sprite bytes across all engine sources")
    parser.add_argument("--execute-build", action="store_true")
    parser.add_argument("--authorize-local-operation", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--after", type=int, default=0)
    parser.add_argument("--limit", type=int, default=16)
    args = parser.parse_args(argv)
    if not args.authorize_local_operation:
        parser.error("explicit local operator authority required")
    try:
        order = parse_campaign_order_file(args.order)
        if args.inspect:
            output = inspect_production_assurance(order, args.campaign)
        elif args.pixel_parity_target:
            if args.pixel_parity_target not in order.targets:
                parser.error("pixel parity target is not in original campaign")
            # The parity tool scans the generated output, not a model narrative.
            output = inspect_cross_engine_pixels(
                args.campaign / "targets" / args.pixel_parity_target
            )
        elif args.dragon_observe:
            output = observe_production_campaign(
                order, args.campaign, authorized=True,
                after=args.after, limit=args.limit,
            )
        elif args.godot_target:
            if not args.execute_build:
                parser.error("--godot-target requires explicit --execute-build")
            output = qualify_campaign_godot(
                order, args.campaign, args.godot_target,
                authorized=True, execute=True,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.browser_target:
            if not args.execute_build:
                parser.error("--browser-target requires explicit --execute-build")
            output = qualify_campaign_browser(
                order, args.campaign, args.browser_target,
                authorized=True, execute=True, timeout_seconds=args.timeout_seconds,
            )
        else:
            if not args.execute_build:
                parser.error("--target requires explicit --execute-build")
            output = qualify_campaign_target(
                order, args.campaign, args.target,
                authorized=True, execute=True,
                timeout_seconds=args.timeout_seconds,
            )
    except (OSError, ValueError, RuntimeError, PermissionError) as exc:
        print(json.dumps({"success": False, "error": type(exc).__name__}, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
