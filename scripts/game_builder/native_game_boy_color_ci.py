"""Compile an original full-color Game Boy Color game and verify CGB hardware metadata."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.ai.game_builder.game_boy_color_native_export import (
    compile_native_game_boy_color, export_native_game_boy_color,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource
from skeleton.ai.game_builder.game_boy_memory_replay import export_game_boy_memory_replay
from scripts.game_builder.native_game_boy_ci import verify_rom


def emit(output: Path) -> dict[str, object]:
    world = generate_playable_world(GameBuildIntent(
        project_id="original-cgb-star-map", title="Original Color Star Maze",
        subtitle="New RGB555 tile art for real Game Boy Color", seed=910762,
        width=17,height=15,levels=3,collectibles_per_level=3,
        hazards_per_level=5,starting_health=4,theme="space",
    ),authorized=True)
    source=HomebrewSource(
        project_id=world.intent.project_id,platform_id="nintendo_game_watch",
        rights_basis="project_owned",evidence_sha256=world.digest,
        creative_identity=("original space puzzle","new multicolor crystal palette","original progression"),
    )
    project=compile_native_game_boy_color(world,source,authorized=True)
    folder=export_native_game_boy_color(project,output,authorized=True)
    export_game_boy_memory_replay(world,folder/"color-hardware-reference.json")
    return {"source_digest":project.content_digest,"world_digest":world.digest,
            "target":"nintendo_game_boy_color","levels":len(world.levels),
            "color_rom_compiled":False,"color_emulator_verified":False}


def verify_cgb(path:Path)->dict[str,object]:
    plain=verify_rom(path)
    blob=path.read_bytes()
    if blob[0x143]!=0xC0:
        raise ValueError("original cartridge is not CGB-only according to Nintendo header")
    plain.update({
        "schema":"skeleton.game_builder.cgb_rgbds_compiled_cartridge.v1",
        "target":"nintendo_game_boy_color",
        "native_color_only_flag_verified":True,
        "rgb555_banked_palette_emulation_verified":False,
        "native_color_gameplay_verified":False,
        "release_approved":False,
        "sha256":sha256(blob).hexdigest(),
    })
    return plain


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--emit",type=Path)
    modes.add_argument("--verify-rom",type=Path)
    args=parser.parse_args()
    result=emit(args.emit) if args.emit is not None else verify_cgb(args.verify_rom)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
