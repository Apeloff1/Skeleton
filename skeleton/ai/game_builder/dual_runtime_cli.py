"""Trusted-local CLI for a dual-runtime, original, playable game source pack.

This is an offline operator entry point, not authentication or publication.
It shares intent validation and replay proof with the existing playable CLI.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from .contracts import canonical_json
from .dual_runtime_export import (
    DualRuntimeExportError,
    export_dual_runtime_package,
    render_dual_runtime_package,
)
from .playable_cli import MAX_INPUT_BYTES, _intent, _read_json
from .playable_compiler import PlayableCompilationError, compile_original_game
from .playable_simulation import GameplayError
from .playable_world import PlayableWorldError


def parser() -> argparse.ArgumentParser:
    entry = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.dual_runtime_cli",
        description="Generate original, proved browser + Godot game project sources offline.",
    )
    entry.add_argument("--intent", required=True, help="Validated original-game intent JSON")
    entry.add_argument("--output", required=True, help="New output directory (must not exist)")
    entry.add_argument(
        "--trusted-local-operator", action="store_true",
        help="Acknowledge externally established operator authorization",
    )
    return entry


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: external authorization acknowledgement required", file=sys.stderr)
        return 2
    try:
        intent = _intent(_read_json(args.intent, MAX_INPUT_BYTES))
        compiled = compile_original_game(intent, authorized=True)
        package = render_dual_runtime_package(compiled, authorized=True)
        output = export_dual_runtime_package(
            package, Path(args.output), authorized=True,
        )
    except (PlayableCompilationError, PlayableWorldError, GameplayError,
            DualRuntimeExportError, OSError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(canonical_json({
        "schema": "skeleton.game_builder.dual_runtime_cli_result.v1",
        "output": str(output),
        "world_digest": package.manifest["world_digest"],
        "manifest_digest": package.manifest["manifest_digest"],
        "proof_status": package.manifest["proof_status"],
        "godot_hardware_tested": False,
        "files": sorted(package.files),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "parser"]
