"""Unified source-verified original game studio release-candidate builder.

Wires the existing expedition engine, seven controller eras, original narrative
canon, procedural 3D asset geometry, independent multi-game Dragon study,
weather QA and Godot 4 player into one authored, reproducible game output.
Never labels a candidate as a shipped game or signs nonexistent legal reviews.
"""
from __future__ import annotations

from hashlib import sha256
from base64 import b64encode
from dataclasses import asdict
from typing import Mapping

from .game_frontier_expedition import (
    ExpeditionError,_digest,_json,Traveler,ExpeditionEpisode,
)
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
from .game_frontier_expedition_quests import original_quest_book
from .game_frontier_expedition_audio import export_original_soundscape
from .game_frontier_expedition_cinematics import (
    original_game_storyboard,storyboard_frame_receipts,export_storyboard_godot,
)
from .game_frontier_expedition_render import (
    View,LODPolicy,render_lod_timeline,
)
from .game_frontier_expedition_dragon_review import (
    adversarial_dragon_review,adversarial_attack_matrix,
)
from .game_frontier_expedition_crash import CrashPolicy
from .game_frontier_expedition_input import (
    AxisBinding,AxisCalibration,
)


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
    dragon_review=adversarial_dragon_review(
        dragon,(world,),player,alternative_budget=3,
    )
    dragon_attacks=adversarial_attack_matrix(dragon,(world,),player)
    questbook=original_quest_book(ExpeditionEpisode(world,player),story)
    storyboard=original_game_storyboard(world,gdd_digest)
    storyboard_frames=storyboard_frame_receipts(storyboard,sample_stride=6)
    sound=export_original_soundscape(world,seconds=1)
    render_frames=render_lod_timeline(
        world,assets["manifest"],(
            View(1,0,0,0,500),
            View(2,35,0,12,500),
            View(3,105,30,25,500),
        ),policy=LODPolicy(triangle_budget=25000),
    )
    crash_policy=CrashPolicy(game_cycles=5)
    qa=run_expedition_qa(
        world.project_id,world.source_digest,
        seeds=(seed,seed+1),islands=islands,alternatives=3,
    )
    release=evaluate_expedition_release(world,player,base_files,qa)
    if release["status"]!="blocked" or release["production_release_approved"]:
        raise ExpeditionError("candidate without legal/native evidence must not be approved")
    files={**native_files,**assets["files"]}
    files["game/frontier/canon.json"]=_json(story.as_dict()).decode("utf-8")
    files["game/frontier/quests.json"]=_json(questbook.as_dict()).decode("utf-8")
    files.update(export_storyboard_godot(storyboard,world))
    files["game/frontier/audio_pcm.json"]=_json({
        "schema":"skeleton.game.original_audio_pcm.v1",
        "world_digest":world.digest,
        "score_digest":sound["score"].digest,
        "rate":sound["score"].sample_rate,
        "wav_sha256":sound["manifest"]["audio_sha256"],
        "pcm_base64":b64encode(sound["wav"][44:]).decode("ascii"),
    }).decode("utf-8")
    files["game/frontier/audio_manifest.json"]=_json(
        sound["manifest"]
    ).decode("utf-8")
    files["game/frontier/lod_runtime.json"]=_json({
        "schema":"skeleton.game.original_lod_runtime.v1",
        "world_digest":world.digest,
        "asset_receipt":assets["manifest"]["receipt_digest"],
        "near_m":80.0,"far_m":240.0,
        "triangle_budget":25000,
        "native_fps_measured":False,
    }).decode("utf-8")
    files["game/frontier/render_journal.json"]=_json(
        render_frames
    ).decode("utf-8")
    files["game/frontier/crash_test_policy.json"]=_json({
        "schema":"skeleton.game.crash_test_policy.v1",
        "world_digest":world.digest,
        "policy":asdict(crash_policy),
        "fault_simulations_executed_by_compiler":False,
    }).decode("utf-8")
    files["game/frontier/visuals_manifest.json"]=_json(assets["manifest"]).decode("utf-8")
    files["game/frontier/dragon_study.json"]=_json(dragon).decode("utf-8")
    files["game/frontier/dragon_adversary.json"]=_json(
        dragon_review
    ).decode("utf-8")
    files["game/frontier/dragon_attacks.json"]=_json(
        dragon_attacks
    ).decode("utf-8")
    files["game/frontier/qa_report.json"]=_json(qa).decode("utf-8")
    files["game/frontier/release_review.json"]=_json(release).decode("utf-8")
    proofs={
        "schema":"skeleton.game.full_original_campaign_candidate.v1",
        "world_digest":world.digest,"source_digest":world.source_digest,
        "gdd_digest":gdd_digest,
        "controller_digest":controller.digest,
        "story_digest":story.digest,
        "questbook_digest":questbook.digest,
        "storyboard_digest":storyboard.digest,
        "cinematic_frame_receipt":storyboard_frames["receipt_digest"],
        "original_audio_receipt":sound["manifest"]["receipt_digest"],
        "render_lod_receipt":render_frames["receipt_digest"],
        "dragon_adversarial_receipt":dragon_review["receipt_digest"],
        "dragon_attack_matrix_receipt":dragon_attacks["receipt_digest"],
        "fault_recovery_budget":asdict(crash_policy),
        "fault_recovery_executed_by_compiler":False,
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
        "story":story,"questbook":questbook,
        "storyboard":storyboard,"audio":sound,
        "render":render_frames,"dragon":dragon,
        "dragon_adversary":dragon_review,
        "dragon_attacks":dragon_attacks,
        "qa":qa,"release_review":release,
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
            or compiled.get("questbook")!=expected["questbook"]
            or compiled.get("storyboard")!=expected["storyboard"]
            or compiled.get("audio")!=expected["audio"]
            or compiled.get("render")!=expected["render"]
            or compiled.get("dragon")!=expected["dragon"]
            or compiled.get("dragon_adversary")!=expected["dragon_adversary"]
            or compiled.get("dragon_attacks")!=expected["dragon_attacks"]
            or compiled.get("qa")!=expected["qa"]):
        raise ExpeditionError("recompiled original game differs from reviewed artifact")
    return {
        "world_digest":expected["world"].digest,
        "campaign_receipt":expected["manifest"]["receipt_digest"],
        "native_engine_executed":False,
        "release_approved":False,
        "all_source_bytes_verified":True,
    }
