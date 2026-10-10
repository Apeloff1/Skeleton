"""Create original authenticated ColecoVision OS7/Z80 console cartridge projects."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.coleco_native_export import (
    compile_native_coleco, export_native_coleco,
)
from skeleton.ai.game_builder.coleco_rom import verify_col
from skeleton.ai.game_builder.playable_world import GameBuildIntent,generate_playable_world
from skeleton.ai.game_builder.game_boy_memory_replay import export_game_boy_memory_replay
from skeleton.ai.game_builder.port_planner import HomebrewSource


def emit(output:Path,*,campaign:bool=False)->dict[str,object]:
    world=generate_playable_world(GameBuildIntent(
        project_id="new-original-colecovision-game",
        title="Original Coleco Star Quest",
        subtitle="New legally authored ColecoVision Z80 maze adventure",
        seed=198210 if campaign else 198207,
        width=17,height=15,levels=8 if campaign else 3,
        collectibles_per_level=6 if campaign else 3,
        hazards_per_level=4,starting_health=4,theme="arcade",
    ),authorized=True)
    rights=HomebrewSource(
        project_id=world.intent.project_id,platform_id="colecovision",
        rights_basis="project_owned",evidence_sha256=world.digest,
        creative_identity=("original new crystal adventure",
                           "independently authored maze maps","own sound cues"),
    )
    project=compile_native_coleco(world,rights,authorized=True)
    root=export_native_coleco(project,output,authorized=True)
    export_game_boy_memory_replay(world,root/"independent-guest-reference.json")
    meta=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    if meta["world_digest"]!=world.digest or meta["native_binary_compiled"]:
        raise ValueError("Coleco machine-source provenance or certification inconsistent")
    return {"game_world_digest":world.digest,"machine_source_sha256":project.content_digest,
            "target":"colecovision","original_levels":len(world.levels),
            "total_original_crystals":sum(len(stage.collectibles) for stage in world.levels),
            "author_campaign_profile":"eight_level_48_crystal" if campaign else "three_level_intro",
            "actual_native_binary_compiled":False,"original_homebrew":True}


def verify(binary:Path,source:Path)->dict[str,object]:
    if not binary.is_file() or not source.is_file():
        raise ValueError("Coleco .col cartridge and native Z80 source binary are both required")
    return verify_col(binary.read_bytes(),source=source.read_bytes())


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    exclusive=parser.add_mutually_exclusive_group(required=True)
    exclusive.add_argument("--emit",type=Path)
    exclusive.add_argument("--verify-rom",type=Path)
    parser.add_argument("--source-bin",type=Path)
    parser.add_argument("--campaign",action="store_true",help="Author full eight-stage 48-gem original ColecoVision game")
    args=parser.parse_args()
    if args.emit is not None:
        report=emit(args.emit,campaign=args.campaign)
    else:
        if args.source_bin is None:
            parser.error("--source-bin is required for --verify-rom")
        report=verify(args.verify_rom,args.source_bin)
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
