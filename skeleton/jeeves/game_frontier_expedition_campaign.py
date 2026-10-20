"""Unified source-verified original game studio release-candidate builder.

Wires the existing expedition engine, seven controller eras, original narrative
canon, procedural 3D asset geometry, independent multi-game Dragon study,
weather QA and Godot 4 player into one authored, reproducible game output.
Never labels a candidate as a shipped game or signs nonexistent legal reviews.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Mapping

from .game_frontier_expedition import ExpeditionError,_digest,_json,Traveler
from .game_frontier_expedition_generation import (
    ArchipelagoProfile,author_archipelago,
)
from .game_frontier_expedition_godot import (
    emit_expedition_godot_project,verify_expedition_godot_project,
)
from .game_frontier_expedition_controllers import (
    profile_for,export_controller_profile,
)
from .game_frontier_expedition_assets import (
    VisualDesign,forge_expedition_assets,verify_expedition_assets,
)
from .game_frontier_expedition_narrative import original_expedition_story
from .game_frontier_expedition_dragon import observe_original_games
from .game_frontier_expedition_qa import run_expedition_qa
from .game_frontier_expedition_release import evaluate_expedition_release


def original_campaign_player()->Traveler:
    return Traveler(
        permitted_modes=frozenset((
            "walk","rope_bridge","updraft","glide",
            "airship","portal","climb","dive","swim",
        )),
        flags=frozenset((
            "glider","airship_license","diving_gear","portal_key",
        )),
        equipment=frozenset(("instrument_navigation",)),
        max_stamina=1000,skill=0.8,
    )


def compile_original_campaign(
    project_id:str, *, gdd_digest:str, seed:int, islands:int=9,
    controller_id:str="dual_stick", visual_design:VisualDesign=VisualDesign(),
)->dict:
    """Actually build full original game files, QA and continuity receipts."""
    profile=ArchipelagoProfile(seed=seed,islands=islands)
    source=_digest({
        "schema":"skeleton.game.campaign_brief.v1",
        "project":project_id,"seed":seed,"islands":islands,"gdd":gdd_digest,
    })
    world=author_archipelago(project_id,source,profile)
    player=original_campaign_player()
    controller=profile_for(controller_id)
    story=original_expedition_story(world,gdd_digest)
    story.validate_world(world)
    assets=forge_expedition_assets(world,visual_design)
    asset_proof=verify_expedition_assets(world,visual_design,assets)
    base_files=emit_expedition_godot_project(
        world,player,include_autoplay=True,
    )
    native_files=emit_expedition_godot_project(
        world,player,include_autoplay=True,controller_profile=controller,
    )
    native_proof=verify_expedition_godot_project(
        native_files,world,player,include_autoplay=True,
        controller_profile=controller,
    )
    dragon=observe_original_games((world,),player,alternative_budget=3)
    qa=run_expedition_qa(
        world.project_id,world.source_digest,
        seeds=(seed,seed+1),islands=islands,alternatives=3,
    )
    release=evaluate_expedition_release(world,player,base_files,qa)
    if release["status"]!="blocked" or release["production_release_approved"]:
        raise ExpeditionError("candidate without legal/native evidence must not be approved")
    files={**native_files,**assets["files"]}
    files["game/frontier/canon.json"]=_json(story.as_dict()).decode("utf-8")
    files["game/frontier/visuals_manifest.json"]=_json(assets["manifest"]).decode("utf-8")
    files["game/frontier/dragon_study.json"]=_json(dragon).decode("utf-8")
    files["game/frontier/qa_report.json"]=_json(qa).decode("utf-8")
    files["game/frontier/release_review.json"]=_json(release).decode("utf-8")
    proofs={
        "schema":"skeleton.game.full_original_campaign_candidate.v1",
        "world_digest":world.digest,"source_digest":world.source_digest,
        "gdd_digest":gdd_digest,
        "controller_digest":controller.digest,
        "story_digest":story.digest,
        "asset_receipt":asset_proof["geometry_receipt"],
        "native_candidate_receipt":native_proof["receipt_digest"],
        "dragon_receipt":dragon["receipt_digest"],
        "qa_receipt":qa["receipt_digest"],
        "release_review_receipt":release["receipt_digest"],
        "unique_game_assets":asset_proof["asset_count"],
        "dragon_verified_route_checks":dragon["metrics"]["verified_objective_routes"],
        "actual_qa_cases":qa["cases_executed"],
        "production_release_approved":False,
        "native_engine_executed_by_compiler":False,
        "external_rights_review_signed":False,
        "file_hashes":{
            path:sha256(content.encode("utf-8")).hexdigest()
            for path,content in sorted(files.items())
        },
    }
    proofs["receipt_digest"]=_digest(proofs)
    files["game/frontier/campaign_provenance.json"]=_json(proofs).decode("utf-8")
    return {
        "world":world,"player":player,
        "files":files,"manifest":proofs,
        "story":story,"dragon":dragon,"qa":qa,"release_review":release,
    }


def verify_original_campaign(compiled:Mapping, *, project_id:str,
                             gdd_digest:str,seed:int,islands:int=9,
                             controller_id:str="dual_stick",
                             visual_design:VisualDesign=VisualDesign())->dict:
    """Independently rebuild *all* game bytes and compare every stage digest."""
    if not isinstance(compiled,Mapping) or not isinstance(compiled.get("files"),Mapping):
        raise ExpeditionError("complete original campaign source required")
    expected=compile_original_campaign(
        project_id,gdd_digest=gdd_digest,seed=seed,islands=islands,
        controller_id=controller_id,visual_design=visual_design,
    )
    if (compiled.get("manifest")!=expected["manifest"]
            or compiled.get("files")!=expected["files"]
            or compiled.get("story")!=expected["story"]
            or compiled.get("dragon")!=expected["dragon"]
            or compiled.get("qa")!=expected["qa"]):
        raise ExpeditionError("recompiled original game differs from reviewed artifact")
    return {
        "world_digest":expected["world"].digest,
        "campaign_receipt":expected["manifest"]["receipt_digest"],
        "native_engine_executed":False,
        "release_approved":False,
        "all_source_bytes_verified":True,
    }
