"""Dedicated zero-network, model-free native 2D game launcher.

PyInstaller builds SkeletonGame.exe directly from this entrypoint.
With --project it opens only an explicitly selected, verified portable
game capsule; without --project it runs the original seeded demo.
No model weights, browser, API key, or proprietary console SDK is used.
"""
from __future__ import annotations

import argparse
from typing import Sequence

from skeleton.app.offline_game_preview import (
    load_game_project, run_game_preview,
)
from skeleton.app.offline_chip8_preview import run_native_chip8_preview
from skeleton.app.homebrew_editor_ui import open_homebrew_editor
from skeleton.app.homebrew_port_ui import open_native_homebrew_port


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="SkeletonGame",
        description="Play a local deterministic 2D game (original or rights-attested capsule).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--project", help="explicit local project capsule to open")
    mode.add_argument("--seed", type=int, help="optional original game seed")
    mode.add_argument("--edit-project", help="open verified original homebrew project editor")
    parser.add_argument("--output", help="new, unused output capsule path for editor Save As")
    parser.add_argument("--port-blueprint", help="verified original-homebrew Windows enhancement blueprint for --project")
    mode.add_argument("--chip8-demo", action="store_true",
                      help="play a genuine original CHIP-8 homebrew ROM in native window")
    args = parser.parse_args(argv)
    if args.output is not None and args.edit_project is None:
        parser.error("--output is only valid with --edit-project")
    if args.port_blueprint is not None and args.project is None:
        parser.error("--port-blueprint requires an explicit original --project")
    if args.edit_project is not None:
        return open_homebrew_editor(args.edit_project, output=args.output)
    if args.chip8_demo:
        return run_native_chip8_preview()
    if args.project is not None:
        if args.port_blueprint is not None:
            return open_native_homebrew_port(args.project, args.port_blueprint)
        return run_game_preview(project_tiles=load_game_project(args.project))
    return run_game_preview() if args.seed is None else run_game_preview(seed=args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
