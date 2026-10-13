"""Genuine original Atari 8-bit 6502/ANTIC program assembly and XEX validation."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.ai.game_builder.native_release_intake import _read_bounded
from skeleton.ai.game_builder.native_retro_artifact import parse_original_atari_xex
from skeleton.ai.game_builder.atari8_native_export import compile_native_atari8, export_native_atari8
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def emit(output: Path) -> dict[str, object]:
    world = generate_playable_world(GameBuildIntent(
        project_id="own-atari-400-800-adventure",
        title="Original Antic Crystal Mazes",
        subtitle="48KB Atari 8-bit homebrew", seed=198307,
        width=19, height=17, levels=3, collectibles_per_level=3,
        hazards_per_level=4, starting_health=4, theme="space",
    ), authorized=True)
    source = HomebrewSource(
        project_id=world.intent.project_id, platform_id="atari_400_800",
        rights_basis="project_owned", evidence_sha256=world.digest,
        creative_identity=("authored maze logic", "original symbols", "new Atari POKEY effects"),
    )
    project = compile_native_atari8(world, source, authorized=True)
    result = export_native_atari8(project, output, authorized=True)
    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["original_world_digest"] == world.digest
    assert manifest["executable_built"] is False
    return {"source_digest": project.content_digest, "world_digest": world.digest,
            "levels": len(world.levels), "native_program_compiled": False}


def verify_xex(path: Path) -> dict[str, object]:
    blob = _read_bounded(path, max_bytes=48*1024-1)
    layout = parse_original_atari_xex(blob)
    return {
        **layout,
        "schema": "skeleton.game_builder.atari8_xex_build_attestation.v1",
        "target": "atari_400_800",
        "format": "atari_8bit_dos_segmented_xex",
        "bytes": len(blob),
        "sha256": sha256(blob).hexdigest(),
        "native_6502_compilation_verified": True,
        "atari_os_emulation_verified": False,
        "atari_hardware_verified": False,
        "distribution_licensed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--emit", type=Path)
    modes.add_argument("--verify-xex", type=Path)
    args = parser.parse_args()
    print(json.dumps(emit(args.emit) if args.emit is not None else verify_xex(args.verify_xex), sort_keys=True))


if __name__ == "__main__":
    main()
