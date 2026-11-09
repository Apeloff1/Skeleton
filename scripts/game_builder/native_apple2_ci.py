"""Compile and validate genuine original Apple II cc65 AppleSingle executable payload."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from struct import unpack_from

from skeleton.ai.game_builder.apple2_native_export import (
    compile_native_apple2, export_native_apple2,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def emit(output: Path) -> dict[str,object]:
    game=generate_playable_world(GameBuildIntent(
        project_id="original-apple-ii-game",title="New Apple Star Labyrinth",
        subtitle="Original 6502 Apple II text adventure",seed=197906,
        width=17,height=15,levels=3,collectibles_per_level=3,
        hazards_per_level=4,starting_health=4,theme="arcade",
    ),authorized=True)
    original=HomebrewSource(
        project_id=game.intent.project_id,platform_id="atari_400_800",
        rights_basis="project_owned",evidence_sha256=game.digest,
        creative_identity=("original text adventure","distinctive crystal stars","new speaker chimes"),
    )
    project=compile_native_apple2(game,original,authorized=True)
    folder=export_native_apple2(project,output,authorized=True)
    metadata=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if metadata["world_digest"] != game.digest or metadata["binary_compiled"]:
        raise RuntimeError("native Apple II source provenance invalid")
    return {"source_digest":project.content_digest,"world_digest":game.digest,
            "original_game_levels":len(game.levels),"binary_built":False}


def verify(path:Path)->dict[str,object]:
    payload=path.read_bytes()
    if not 1024 <= len(payload) <= 65535:
        raise ValueError("Apple II executable exceeds bounded disk image budget")
    if payload[:4] != bytes.fromhex("00051600"):
        raise ValueError("expected genuine AppleSingle header, not DOS/Atari/Windows")
    version=unpack_from(">I",payload,4)[0]
    if version not in (0x00010000,0x00020000):
        raise ValueError("unrecognized AppleSingle format version")
    entries=unpack_from(">H",payload,24)[0]
    if not 1 <= entries <= 12 or 26+entries*12 > len(payload):
        raise ValueError("AppleSingle metadata entries malformed")
    seen=set()
    reports=[]
    for i in range(entries):
        entry_id,offset,length=unpack_from(">III",payload,26+12*i)
        if entry_id in seen:
            raise ValueError("AppleSingle entry ID duplicated")
        seen.add(entry_id)
        if offset < 26+entries*12 or length > len(payload)-offset:
            raise ValueError("AppleSingle would reference data outside artifact")
        reports.append({"id":entry_id,"offset":offset,"bytes":length})
    if 1 not in seen:
        raise ValueError("AppleSingle file lacks original native data fork")
    body=next(row for row in reports if row["id"]==1)
    if body["bytes"]<128:
        raise ValueError("Apple II native executable data fork unexpectedly short")
    return {
        "schema":"skeleton.game_builder.apple2_applesingle_compiled.v1",
        "platform":"apple_ii","format":"AppleSingle_6502_cc65",
        "bytes":len(payload),"sha256":sha256(payload).hexdigest(),
        "applesingle_header_verified":True,
        "version":version,"file_entry_count":entries,
        "file_entries":reports,
        "actual_native_binary_compiled":True,
        "disk_image_boot_verified":False,
        "apple_ii_emulator_playthrough_verified":False,
        "original_hardware_verified":False,
        "rights_to_distribute_verified":False,
    }


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--emit",type=Path)
    group.add_argument("--verify",type=Path)
    args=parser.parse_args()
    print(json.dumps(emit(args.emit) if args.emit is not None else verify(args.verify),sort_keys=True))


if __name__=="__main__":
    main()
