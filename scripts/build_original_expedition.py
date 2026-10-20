#!/usr/bin/env python3
"""Author, export, and optionally execute a real original Godot 4 expedition.

Preview executes the deterministic gameplay simulator; --native invokes
Godot and validates its stdout independently. No missing-engine fallbacks.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from skeleton.jeeves.game_frontier_expedition import ExpeditionError, Traveler, _json
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile, author_archipelago, playtest_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_godot import (
    emit_expedition_godot_project, verify_expedition_godot_project,
)
from skeleton.jeeves.game_frontier_expedition_native_runner import run_headless_expedition


def original_player() -> Traveler:
    return Traveler(
        permitted_modes=frozenset(("walk","rope_bridge","updraft","glide",
            "airship","portal","climb","dive","swim")),
        flags=frozenset(("glider","airship_license","diving_gear","portal_key")),
        equipment=frozenset(("instrument_navigation",)),
        max_stamina=1000,skill=0.8,
    )


def build_original_expedition(
    project_id: str, *, seed: int, islands: int, native: bool = False,
    godot_executable: str | None = None,
) -> tuple[dict[str,str],dict]:
    if type(native) is not bool:
        raise ExpeditionError("native execution must be an explicit boolean")
    profile=ArchipelagoProfile(seed=seed,islands=islands)
    brief={"schema":"skeleton.game.original_expedition_brief.v1",
           "project":project_id,"seed":profile.seed,"islands":profile.islands,
           "authoring_mode":"original_seeded_game_build"}
    world=author_archipelago(project_id,sha256(_json(brief)).hexdigest(),profile)
    player=original_player()
    played=playtest_archipelago(world,max_routes=4)
    files=emit_expedition_godot_project(world,player,include_autoplay=True)
    verified=verify_expedition_godot_project(
        files,world,player,include_autoplay=True)
    native_receipt=(run_headless_expedition(
        world,player,godot_executable=godot_executable) if native else None)
    report={
        "schema":"skeleton.game.original_expedition_build.v1",
        "source_digest":world.source_digest,
        "world_digest":world.digest,"project_id":world.project_id,
        "waypoint_count":len(world.waypoints),
        "connected_edges":len(world.by_edge),
        "actual_simulated_routes":played["routes_executed"],
        "route_playthrough_receipt":played["receipt_digest"],
        "native_candidate_receipt":verified["receipt_digest"],
        "native_executed":bool(native_receipt),
        "native_playthrough_receipt":(
            native_receipt["receipt_digest"] if native_receipt else None),
        "canonical_file_hashes":verified["file_hashes"],
        "independent_native_engine_signoff":False,
        "full_original_masterplan_completed":False,
    }
    report["receipt_digest"]=sha256(_json(report)).hexdigest()
    return files,report


def export_new_game(destination: Path, files: dict[str,str]) -> None:
    """Atomically publish a never-before-existing game, without overwrites."""
    if not isinstance(destination,Path):
        raise ExpeditionError("export destination must be a path")
    target=destination.absolute()
    if target.exists() or target.is_symlink():
        raise ExpeditionError("destination exists; game source not replaced")
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=target.parent,prefix=".original-expedition-",
    ) as folder:
        root=Path(folder)
        for relative,source in files.items():
            path=Path(relative)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ExpeditionError("unsafe generated game file path")
            output=root/path
            output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(source,encoding="utf-8")
        os.replace(root,target)


def main(argv=None) -> int:
    p=argparse.ArgumentParser(
        description="Build original playable multi-route Godot 4 games")
    p.add_argument("--project-id",required=True)
    p.add_argument("--seed",type=int,default=742193)
    p.add_argument("--islands",type=int,default=12)
    p.add_argument("--export",type=Path)
    p.add_argument("--native",action="store_true")
    p.add_argument("--godot")
    args=p.parse_args(argv)
    try:
        files,report=build_original_expedition(
            args.project_id,seed=args.seed,islands=args.islands,
            native=args.native,godot_executable=args.godot)
        if args.export:
            export_new_game(args.export,files)
        print(json.dumps(report,indent=2,sort_keys=True))
        return 0
    except (ExpeditionError,OSError) as exc:
        p.exit(2,"Expedition build blocked: "+str(exc)+"\n")


if __name__=="__main__":
    raise SystemExit(main())
