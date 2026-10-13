"""Build and validate an actual native ZX Spectrum 48K CODE tape game."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.ai.game_builder.spectrum_native_export import (
    compile_native_spectrum, export_native_spectrum,
)
from skeleton.ai.game_builder.spectrum_tap import verify_tape
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def emit(output: Path) -> dict[str,object]:
    world=generate_playable_world(GameBuildIntent(
        project_id="original-zx-spectrum-star-world",
        title="ZX Star Labyrinth",subtitle="A genuinely original Spectrum 48K game",
        seed=198209,width=17,height=15,levels=3,
        collectibles_per_level=3,hazards_per_level=4,
        starting_health=4,theme="arcade",
    ), authorized=True)
    rights=HomebrewSource(
        project_id=world.intent.project_id,platform_id="sinclair_zx_spectrum",
        rights_basis="project_owned",evidence_sha256=world.digest,
        creative_identity=("original Spectrum maze","my unique stars and crystal glyphs","distinct rule system"),
    )
    project=compile_native_spectrum(world,rights,authorized=True)
    folder=export_native_spectrum(project,output,authorized=True)
    receipt=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if receipt["world_digest"]!=world.digest or receipt["native_binary_compiled"]:
        raise ValueError("Spectrum native world authenticity metadata inconsistent")
    return {"source_digest":project.content_digest,"world_digest":world.digest,
            "levels":len(world.levels),"binary_compiled":False}


def verify(tape:Path,binary:Path)->dict[str,object]:
    if not tape.is_file() or not binary.is_file():
        raise ValueError("actual TAP and native Z80 program required")
    info=verify_tape(tape.read_bytes(),binary.read_bytes())
    info["native_z80_source_assembled"]=True
    info["rom_loading_or_emulator_playthrough_verified"]=False
    return info


def main()->None:
    ap=argparse.ArgumentParser(description=__doc__)
    m=ap.add_mutually_exclusive_group(required=True)
    m.add_argument("--emit",type=Path)
    m.add_argument("--verify-tap",type=Path)
    ap.add_argument("--binary",type=Path)
    args=ap.parse_args()
    if args.emit is not None:
        result=emit(args.emit)
    else:
        if args.binary is None:
            ap.error("--binary required for --verify-tap")
        result=verify(args.verify_tap,args.binary)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
