"""Portable command-line port builder for ORIGINAL homebrew -> native Windows.

Creates only a checked, non-executable JSON *port blueprint* consumed
by the existing SkeletonGame.exe. No copied console executable, ROM,
protected assets, third-party game conversion, remote toolchain,
copyright-avoidance laundering or automatic publisher signoff.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from scripts.game.game_project import _read_json, _write_new
from skeleton.ai.runtime.homebrew_porting import (
    ART_DIRECTIONS, CREATIVE_MODES, DESTINATIONS,
    HYBRID_MODES, QUALITY, HomebrewPortError,
    make_homebrew_port, verify_homebrew_port, verify_port_gameplay,
)


def _parse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Advance an ORIGINAL homebrew game's visuals/gameplay when porting to Windows.",
    )
    parser.add_argument("--capsule", type=Path, required=True,
                        help="a verified original homebrew project capsule")
    parser.add_argument("--verify", type=Path, help="verify stored port blueprint only")
    parser.add_argument("--output", type=Path, help="write a new original Windows port blueprint")
    parser.add_argument("--destination", choices=DESTINATIONS, default="windows-native")
    parser.add_argument("--creative-mode", choices=CREATIVE_MODES,
                        default="enhanced_homebrew")
    parser.add_argument("--art-direction", choices=tuple(ART_DIRECTIONS),
                        default="neon_noir")
    parser.add_argument("--quality", choices=QUALITY, default="enhanced")
    parser.add_argument("--hybrids", default="",
                        help="comma-separated original modes: " + ",".join(HYBRID_MODES))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scale", type=int, default=32)
    parser.add_argument("--decor-budget", type=int, default=24)
    parser.add_argument("--reduced-motion", action="store_true")
    parser.add_argument("--high-contrast", action="store_true")
    parser.add_argument("--colorblind-safe", action="store_true")
    parser.add_argument("--no-hud", action="store_true")
    parser.add_argument("--no-parallax", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    p = _parse()
    args = p.parse_args(argv)
    if bool(args.verify) == bool(args.output):
        p.error("choose exactly one of --output (new) or --verify (existing)")
    if args.verify is not None and any((
        args.destination != "windows-native",
        args.creative_mode != "enhanced_homebrew",
        args.art_direction != "neon_noir",
        args.quality != "enhanced", args.hybrids != "",
        args.seed != 42, args.scale != 32, args.decor_budget != 24,
        args.reduced_motion, args.high_contrast, args.colorblind_safe,
        args.no_hud, args.no_parallax,
    )):
        p.error("--verify reads only the stored blueprint, not authoring overrides")
    try:
        source = _read_json(args.capsule)
        if args.verify is not None:
            blueprint = _read_json(args.verify)
        else:
            blueprints = [
                item for item in args.hybrids.split(",") if item
            ]
            blueprint = make_homebrew_port(
                source, destination=args.destination,
                creative_mode=args.creative_mode,
                art_direction=args.art_direction, quality=args.quality,
                hybrids=blueprints, seed=args.seed,
                scale=args.scale, decor_budget=args.decor_budget,
                reduced_motion=args.reduced_motion,
                high_contrast=args.high_contrast,
                colorblind_safe=args.colorblind_safe,
                hud=not args.no_hud, parallax=not args.no_parallax,
            )
        checked = verify_homebrew_port(source, blueprint)
        played = verify_port_gameplay(source, blueprint)
        path = _write_new(args.output, blueprint) if args.output else None
        print(json.dumps({
            **checked,
            "actual_hybrid_gameplay": played,
            "output_path": path,
            "source_is_original_homebrew": True,
            "does_not_reproduce_a_copyrighted_title": "not_independently_established",
            "rights_review_still_needed": True,
            "windows_native_executable_rebuilt": False,
            "training_examples_added": 0,
        }, sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(
            "original homebrew Windows port rejected: " + str(exc),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
