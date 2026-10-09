"""Executable acceptance for every implemented legal-first game output.

Run actual CHIP-8 machine code to win, compile and RUN an original ISO
C89 game to WIN, and replay a real native 2D preview to its goal.
No internet, hidden model, training, SDK, copyrighted game input or
synthetic "pass" based on a file's mere existence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence

from scripts.game.export_chip8 import (
    _original_capsule, compile_chip8_homebrew, verify_chip8_executable,
)
from scripts.game.export_portable_c89 import emit_portable_c89
from scripts.game.game_project import _demo
from skeleton.app.offline_game_preview import verify_game_preview
from skeleton.ai.runtime.gameplay_capabilities import compile_level
from skeleton.ai.runtime.game_project_capsule import verify_game_capsule
from skeleton.ai.runtime.homebrew_porting import make_homebrew_port, verify_port_gameplay
from scripts.windows.create_offline_game_fixture import create_fixture

SCHEMA = "skeleton.game.executed_acceptance.v1"


class GameAcceptanceError(RuntimeError):
    """No final acceptance without a complete, actual playable result."""


def _accept_c89(compiler: str | None) -> dict[str, Any]:
    if compiler is None:
        raise GameAcceptanceError("no C89 compiler was found; C89 game remains unverified")
    project = _demo(42, ["ibm-pc-dos", "windows-11"], "NO")
    verified = verify_game_capsule(project)
    artifact = emit_portable_c89(project)
    level = compile_level({"tiles": project["tilemap"]})
    # The original map generator carves a horizontal top path to the
    # right boundary followed by the vertical goal corridor.
    moves = (
        "d" * (level["goal"]["x"] - level["spawn"]["x"])
        + "s" * (level["goal"]["y"] - level["spawn"]["y"])
        + "\n"
    )
    with tempfile.TemporaryDirectory(prefix="skeleton-game-accept-") as folder:
        source = Path(folder) / "original.c"
        compiled = Path(folder) / ("original.exe" if sys.platform == "win32" else "original")
        source.write_text(artifact["source"], encoding="ascii")
        try:
            build = subprocess.run(
                [compiler, "-std=c89", "-Wall", "-Wextra", "-Werror",
                 "-pedantic", str(source), "-o", str(compiled)],
                text=True, capture_output=True, timeout=45, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GameAcceptanceError("portable C89 compilation failed") from exc
        if build.returncode != 0 or not compiled.is_file():
            raise GameAcceptanceError(
                "ISO C89 compiler returned an error: " + build.stderr[-1200:]
            )
        try:
            played = subprocess.run(
                [str(compiled)], input=moves, text=True,
                capture_output=True, timeout=12, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GameAcceptanceError("compiled C89 game did not finish") from exc
        if (
            played.returncode != 0 or "WIN" not in played.stdout
            or "BLOCKED" in played.stdout
        ):
            raise GameAcceptanceError("compiled C89 game failed real input-to-win path")
        return {
            "source_sha256": artifact["source_sha256"],
            "source_capsule_sha256": verified["capsule_sha256"],
            "compiled_binary_sha256": hashlib.sha256(compiled.read_bytes()).hexdigest(),
            "compiled_and_actually_won": True,
            "input_events": len(moves.strip()),
            "proprietary_sdk_used": False,
            "original_assets_only": True,
            "actual_era_hardware_verified": False,
            "publish_authorized": False,
        }


def execute_all_available_game_acceptance() -> dict[str, Any]:
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    portable = _accept_c89(compiler)
    retro = compile_chip8_homebrew(_original_capsule(42))
    retro_proof = verify_chip8_executable(retro)
    if not retro_proof["win_state_reached"]:
        raise GameAcceptanceError("CHIP-8 emitted bytecode did not reach winning state")
    native = verify_game_preview(42)
    if not native["terminal_won"] or not native["replay_deterministic"]:
        raise GameAcceptanceError("native gameplay was not completed deterministically")
    # Destination enhancement is a *fourth* actual gameplay output:
    # the original homebrew source must still WIN with independently
    # replayed Windows art/UX enhancements and five interacting hybrids.
    windows_source = create_fixture(42)
    windows_blueprint = make_homebrew_port(
        windows_source,
        creative_mode="hybrid_original", art_direction="neon_noir",
        quality="cinematic", seed=42, scale=40,
        hybrids=["collectathon", "keyquest", "speedrun", "exploration", "combo"],
        high_contrast=True, decor_budget=36,
    )
    windows_acceptance = verify_port_gameplay(
        windows_source, windows_blueprint,
    )
    if (
        not windows_acceptance["hybrid_gameplay_proven"]
        or not windows_acceptance["original_gameplay_proven"]
        or windows_acceptance["remaining_collectibles"] != 0
        or not windows_acceptance["deterministic"]
    ):
        raise GameAcceptanceError(
            "enhanced original Windows port failed actual hybrid win acceptance"
        )
    return {
        "schema_version": SCHEMA,
        "accepted_execution_targets": [
            "portable-iso-c89-original-turn-based",
            "chip8-vip-original-homebrew-vm",
            "native-2d-preview-headless",
            "native-windows-enhanced-original-hybrid",
        ],
        "portable_c89": portable,
        "chip8_original_rom": {
            "rom_sha256": retro["rom_sha256"],
            "rom_bytes": retro["rom_bytes"],
            "win_state_reached": retro_proof["win_state_reached"],
            "input_events": retro_proof["input_events_used"],
            "machine_interpreter_used": True,
            "real_vintage_hardware_verified": False,
            "legal_publication_approved": False,
        },
        "native_preview": {
            "replay_sha256": native["replay_sha256"],
            "terminal_won": native["terminal_won"],
            "frames_verified": native["frames_verified"],
            "display_opened": False,
            "installed_windows_binary_verified": False,
        },
        "windows_homebrew_port": {
            "source_capsule_sha256": windows_source["capsule_sha256"],
            "port_sha256": windows_blueprint["port_sha256"],
            "real_hybrid_win_replayed": windows_acceptance["hybrid_gameplay_proven"],
            "original_gameplay_preserved": windows_acceptance["original_gameplay_proven"],
            "remaining_keys_at_win": windows_acceptance["remaining_collectibles"],
            "source_physics_untouched": windows_blueprint["render"]["source_collision_map_unchanged"],
            "actual_windows_display_opened": False,
            "commercial_assets_imported": False,
            "legal_distribution_approved": False,
        },
        "all_implemented_gameplay_outputs_executed": True,
        "all_platform_releases_completed": False,
        "full_legal_publication_signoff": False,
        "training_examples_added": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute real C89 binary, CHIP-8 ROM and native game to win; fail on missing compiler.",
    )
    parser.parse_args(argv)
    try:
        print(json.dumps(
            execute_all_available_game_acceptance(),
            sort_keys=True,
        ))
        return 0
    except (GameAcceptanceError, ValueError, OSError, TypeError) as exc:
        print("executed game acceptance FAILED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
