#!/usr/bin/env python3
"""Compile and independently verify a full original Godot 4 campaign.

No copyrighted game data, automatic legal signoff or fake AI weight training.
Native execution remains a separately verified Godot runner. This command
publishes a *new* source-bound game directory atomically, never overwriting
an existing project.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_campaign import (
    compile_original_campaign,verify_original_campaign,
)
from skeleton.jeeves.game_frontier_expedition_assets import VisualDesign
from scripts.build_original_expedition import export_new_game


def build_full_original_campaign(project_id:str, *,
    gdd_digest:str,seed:int,islands:int,controller_id:str="dual_stick",
    detail:float=0.25,destination:Path|None=None,
)->dict:
    design=VisualDesign(seed=seed,detail_scale=detail)
    candidate=compile_original_campaign(
        project_id,gdd_digest=gdd_digest,seed=seed,islands=islands,
        controller_id=controller_id,visual_design=design,
    )
    review=verify_original_campaign(
        candidate,project_id=project_id,gdd_digest=gdd_digest,
        seed=seed,islands=islands,controller_id=controller_id,
        visual_design=design,
    )
    if destination is not None:
        export_new_game(destination,candidate["files"])
    manifest=candidate["manifest"]
    return {
        "schema":"skeleton.game.original_campaign_cli_report.v1",
        "project":project_id,
        "world_digest":manifest["world_digest"],
        "gdd_digest":manifest["gdd_digest"],
        "source_files":len(candidate["files"]),
        "original_generated_meshes":manifest["unique_game_assets"],
        "original_npc_cast":manifest["npc_cast_count"],
        "original_skeletal_rig_digest":manifest["rig_digest"],
        "elastic_skin_receipt":manifest["elastic_skin_receipt"],
        "faction_economy_receipt":manifest["npc_society_receipt"],
        "facial_performance_receipt":manifest["performance_receipt"],
        "dragon_visual_receipt":manifest["dragon_visual_receipt"],
        "controller_latency_receipt":manifest["controller_latency_receipt"],
        "production_watchdog_receipt":manifest["production_watchdog_receipt"],
        "release_planes_source_checked":manifest["seven_plane_source_checks"],
        "original_foliage_instances":candidate["ecology"]["instance_count"],
        "source_replayed_story_branches":manifest["full_branch_playthroughs"],
        "source_replayed_distinct_endings":manifest["different_endings_earned"],
        "native_camera_frame_verification_required":True,
        "generated_adaptive_music_receipt":manifest["adaptive_music_receipt"],
        "dragon_source_note_promotion_automatic":False,
        "narrative_and_game_canon_replay_required":True,
        "executed_qa_scenarios":manifest["actual_qa_cases"],
        "dragon_independently_replayed_objective_routes":manifest["dragon_verified_route_checks"],
        "controller_profile":controller_id,
        "canonical_story_digest":manifest["story_digest"],
        "game_manifest_receipt":manifest["receipt_digest"],
        "independent_recompile_verified":review["all_source_bytes_verified"],
        "native_executed":False,
        "production_release_approved":False,
    }


def main(argv=None)->int:
    parser=argparse.ArgumentParser(
        description="Author a complete original sky-island Godot campaign",
    )
    parser.add_argument("--project-id",required=True)
    parser.add_argument("--gdd-sha256",required=True)
    parser.add_argument("--seed",type=int,default=742193)
    parser.add_argument("--islands",type=int,default=9)
    parser.add_argument("--controller",default="dual_stick")
    parser.add_argument("--detail",type=float,default=0.25)
    parser.add_argument("--export",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=build_full_original_campaign(
            args.project_id,gdd_digest=args.gdd_sha256,
            seed=args.seed,islands=args.islands,
            controller_id=args.controller,detail=args.detail,
            destination=args.export,
        )
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except (ExpeditionError,OSError) as exc:
        parser.exit(2,"Original game build blocked: "+str(exc)+"\n")


if __name__=="__main__":
    raise SystemExit(main())
