"""Compile and independently validate authentic original MSX1 Z80 cartridge ROM."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.msx1_native_export import (
    compile_native_msx1, export_native_msx1,
)
from skeleton.ai.game_builder.msx1_rom import verify_msx1_rom
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def emit(output: Path) -> dict[str, object]:
    world=generate_playable_world(GameBuildIntent(
        project_id="new-msx1-star-adventure", title="MSX Star Voyage",
        subtitle="Original 16KB Z80 BIOS MSX1 homebrew", seed=198306,
        width=17,height=15,levels=3,collectibles_per_level=3,
        hazards_per_level=4,starting_health=4,theme="arcade",
    ),authorized=True)
    author=HomebrewSource(
        project_id=world.intent.project_id,platform_id="msx1",
        rights_basis="project_owned",evidence_sha256=world.digest,
        creative_identity=("own original MSX1 gameplay","new puzzle stages","author-created star art"),
    )
    project=compile_native_msx1(world,author,authorized=True)
    folder=export_native_msx1(project,output,authorized=True)
    metadata=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if metadata["world_digest"]!=world.digest or metadata["native_rom_built"]:
        raise ValueError("native original MSX1 game source provenance violated")
    return {
        "source_digest":project.content_digest,"world_digest":world.digest,
        "gameplay_levels":len(world.levels),"native_binary_built":False,
        "native_emulator_playthrough_verified":False,
    }


def verify(rom:Path,code:Path)->dict[str, object]:
    if not rom.is_file() or not code.is_file():
        raise ValueError("actual native MSX ROM and assembled original Z80 required")
    return verify_msx1_rom(rom.read_bytes(),expected_program=code.read_bytes())


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--emit",type=Path)
    modes.add_argument("--verify-rom",type=Path)
    parser.add_argument("--binary",type=Path)
    args=parser.parse_args()
    if args.emit is not None:
        report=emit(args.emit)
    else:
        if args.binary is None:
            parser.error("--binary required for independent MSX1 cartridge verification")
        report=verify(args.verify_rom,args.binary)
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
