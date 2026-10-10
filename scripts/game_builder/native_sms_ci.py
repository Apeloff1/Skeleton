"""Compile native Sega Master System 32KB Z80 Mode4 cartridge from authored world."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.sms_native_export import (
    compile_native_sms,export_native_sms,
)
from skeleton.ai.game_builder.sms_rom import verify_sms
from skeleton.ai.game_builder.playable_world import GameBuildIntent,generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def emit(output:Path)->dict[str,object]:
    world=generate_playable_world(GameBuildIntent(
        project_id="new-sega-sms-homebrew-stars",
        title="Original Sega Starfall",subtitle="Entirely new authored Master System Z80 puzzle",
        seed=198605,width=17,height=15,levels=3,collectibles_per_level=3,
        hazards_per_level=4,starting_health=4,theme="arcade",
    ),authorized=True)
    rights=HomebrewSource(
        project_id=world.intent.project_id,platform_id="sega_master_system",
        rights_basis="project_owned",evidence_sha256=world.digest,
        creative_identity=("independently authored stars","new 4bpp Mode4 assets","original puzzle route"),
    )
    project=compile_native_sms(world,rights,authorized=True)
    root=export_native_sms(project,output,authorized=True)
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    if manifest["world_digest"]!=world.digest or manifest["native_cartridge_compiled"]:
        raise ValueError("SMS original game identity or build certification incorrect")
    return {"source_digest":project.content_digest,"world_digest":world.digest,
            "target":"sega_master_system","stages":len(world.levels),
            "native_binary_built":False}


def verify(rom:Path,program:Path)->dict[str,object]:
    if not rom.is_file() or not program.is_file():
        raise ValueError("SMS Z80 program and actual native cartridge both required")
    return verify_sms(rom.read_bytes(),expected_program=program.read_bytes())


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--emit",type=Path)
    modes.add_argument("--verify-rom",type=Path)
    parser.add_argument("--binary",type=Path)
    args=parser.parse_args()
    if args.emit is not None:
        out=emit(args.emit)
    else:
        if args.binary is None:
            parser.error("--binary required to independently certify compiled Sega ROM")
        out=verify(args.verify_rom,args.binary)
    print(json.dumps(out,sort_keys=True))


if __name__=="__main__":
    main()
