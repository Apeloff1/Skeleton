"""Build genuine original Motorola 6809 Vectrex vector CRT homebrew source."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.vectrex_native_export import (
    compile_native_vectrex,export_native_vectrex,
)
from skeleton.ai.game_builder.vectrex_rom import verify_vectrex
from skeleton.ai.game_builder.playable_world import GameBuildIntent,generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def emit(out:Path)->dict[str,object]:
    world=generate_playable_world(GameBuildIntent(
        project_id="original-6809-vectrex-star-dragon",
        title="Original Vector Dragon Stars",
        subtitle="Independently authored pure-vector 6809 maze game",
        seed=198212,width=17,height=15,levels=3,
        collectibles_per_level=3,hazards_per_level=4,
        starting_health=4,theme="arcade",
    ),authorized=True)
    owned=HomebrewSource(
        project_id=world.intent.project_id,platform_id="vectrex",
        rights_basis="project_owned",evidence_sha256=world.digest,
        creative_identity=("my vector dragon companion",
                           "original star crystal maze","authored vector wing and hazard motifs"),
    )
    project=compile_native_vectrex(world,owned,authorized=True)
    folder=export_native_vectrex(project,out,authorized=True)
    meta=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if meta["world_digest"]!=world.digest or meta["compiled_rom"] is not False:
        raise ValueError("Vectrex source world author-custody or certification invalid")
    return {"target":"vectrex","world_digest":world.digest,
            "original_levels":len(world.levels),
            "6809_source_content_digest":project.content_digest,
            "genuine_cart_compiled":False,
            "hardware_emulator_verified":False}


def main()->None:
    ap=argparse.ArgumentParser(description=__doc__)
    a=ap.add_mutually_exclusive_group(required=True)
    a.add_argument("--emit",type=Path)
    a.add_argument("--verify",type=Path)
    args=ap.parse_args()
    print(json.dumps(emit(args.emit) if args.emit is not None
                     else verify_vectrex(args.verify.read_bytes()),sort_keys=True))


if __name__=="__main__":
    main()
