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
from .game_frontier_expedition_plot_audit import prove_original_story_branches
from .game_frontier_expedition_session import ProductionSession
from .game_frontier_expedition_audio_mix import (
    make_original_ambient_layers,mix_original_stems,
)
from .game_frontier_expedition_npcs import original_world_npcs,NPCEpisode
from .game_frontier_expedition_ecology import (
    EcologyPolicy,generate_original_ecology,export_ecology_godot,
    simulate_ecology_frame,
)
from .game_frontier_expedition_input import (
    AxisBinding,AxisCalibration,
)
from .game_frontier_expedition_animation import (
    original_actor_rig,simulate_elastic_skin,export_actor_rig_godot,
)
from .game_frontier_expedition_society import simulate_original_society
from .game_frontier_expedition_performance import (
    author_performance,export_performance_godot,
)
from .game_frontier_expedition_visual_lab import (
    original_procedural_preview_frames,compare_original_visuals,
)
from .game_frontier_expedition_controller_latency import (
    qualify_game_controller,simulated_controller_trace,
)
from .game_frontier_expedition_watchdog import simulate_production_health
from .game_frontier_expedition_seven_review import objectively_review_seven_planes
from .game_frontier_ik import solve_foot_plant
from .game_frontier_ragdoll import simulate_ragdoll
from .game_frontier_supply import original_supply_network
from .game_frontier_blocking import author_original_blocking,export_blocking_godot
from .game_frontier_visual_capture import export_native_capture_godot
from .game_frontier_postproduction import compile_frame_postproduction
from .game_frontier_controller_parity import verify_all_controller_eras
from .game_frontier_soak import simulated_process_recovery
from .game_frontier_campaign_seven_audits import (
    compile_seven_campaign_audits, verify_seven_campaign_audits,
)
from .game_frontier_expedition_world_assurance import compile_world_assurance,verify_world_assurance
from .game_frontier_expedition_navigation_advanced import (
    compile_navigation_seven, verify_navigation_seven,
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
    world_assurance=compile_world_assurance(world,player,story,questbook)
    verify_world_assurance(world,player,story,questbook,world_assurance)
    storyboard=original_game_storyboard(world,gdd_digest)
    storyboard_frames=storyboard_frame_receipts(storyboard,sample_stride=6)
    sound=export_original_soundscape(world,seconds=1)
    mix=mix_original_stems(make_original_ambient_layers(sound["score"]))
    branch_proof=prove_original_story_branches(world,player,story,questbook)
    ecology_policy=EcologyPolicy(seed=seed,per_waypoint=12)
    ecology=generate_original_ecology(world,ecology_policy)
    ecology_sample=simulate_ecology_frame(ecology,frame=120,wind_mps=10)
    npc_designs=original_world_npcs(world)
    npc_records=[]
    for design in npc_designs:
        actual=NPCEpisode(world,player,design)
        for tick in range(1,4):
            actual.choose(player_at=world.arrival,player_reputation=0,tick=tick)
        observed=NPCEpisode.restore(world,player,design,actual.snapshot())
        if observed.snapshot()!=actual.snapshot():
            raise ExpeditionError("NPC independent build replay differed")
        npc_records.append({"design":asdict(design),"proof":actual.snapshot()})
    # Seven additional independently replayable original game-production systems.
    rig,walk_cycle=original_actor_rig(world.digest)
    soft_skin=simulate_elastic_skin(rig,walk_cycle,frames=48)
    ik=solve_foot_plant(rig,frame=18)
    ragdoll=simulate_ragdoll(rig,frames=36)
    supply=original_supply_network(world,tuple(npc_designs))
    blocking=author_original_blocking(world,storyboard,tuple(npc_designs))
    parity=verify_all_controller_eras(world.digest)
    soak=simulated_process_recovery(world.digest,cycles=6)
    society=simulate_original_society(world,tuple(npc_designs))
    performance=author_performance(story,storyboard)
    preview_rgb=(original_procedural_preview_frames(world.digest),)
    vision=compare_original_visuals(preview_rgb)
    postproduction=compile_frame_postproduction(preview_rgb[0],expected_world=world.digest)
    measured_controller=qualify_game_controller(
        controller,simulated_controller_trace(controller),
        world_digest=world.digest,
    )
    watchdog=simulate_production_health(world.digest,ticks=12)
    seven_axes=objectively_review_seven_planes(world.digest,{
        "rig":{"rig_digest":rig.digest,"soft_body_receipt":soft_skin["receipt_digest"],
               "world":world.digest},
        "society":society,
        "performance":performance,
        "dragon_vision":vision,
        "controller_latency":measured_controller,
        "production_watchdog":watchdog,
        "rights_and_native":{
            "world":world.digest,"rights_signed":False,
            "native_game_executed":False,"physical_controller_verified":False,
            "long_duration_days":0,
        },
    })
    if seven_axes["production_release_approved"] or seven_axes["passed"]!=6:
        raise ExpeditionError("original studio cannot bypass unsigned release assurance")
    seven_campaign_audits=compile_seven_campaign_audits(world,player,assets)
    verify_seven_campaign_audits(world,player,assets,seven_campaign_audits)
    advanced_navigation=compile_navigation_seven(world,player)
    verify_navigation_seven(world,player,advanced_navigation)
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
    files["game/frontier/world_assurance.json"]=_json(world_assurance).decode("utf-8")
    files["game/frontier/canon.json"]=_json(story.as_dict()).decode("utf-8")
    files["game/frontier/quests.json"]=_json(questbook.as_dict()).decode("utf-8")
    files.update(export_storyboard_godot(storyboard,world))
    files.update(export_ecology_godot(world,ecology_policy))
    files.update(export_actor_rig_godot(rig,walk_cycle))
    files.update(export_performance_godot(story,storyboard))
    files.update(export_blocking_godot(world,storyboard,tuple(npc_designs)))
    files.update(export_native_capture_godot())
    files["game/frontier/foot_ik.json"]=_json(ik).decode("utf-8")
    files["game/frontier/ragdoll.json"]=_json(ragdoll).decode("utf-8")
    files["game/frontier/supply_chain.json"]=_json(supply).decode("utf-8")
    files["game/frontier/controller_era_parity.json"]=_json(parity).decode("utf-8")
    files["game/frontier/process_soak.json"]=_json(soak).decode("utf-8")
    files["game/frontier/elasticbodyskin3d.json"]=_json(soft_skin).decode("utf-8")
    files["game/frontier/society.json"]=_json(society).decode("utf-8")
    files["game/frontier/visual_comparison.json"]=_json(vision).decode("utf-8")
    files["game/frontier/postproduction.json"]=_json(postproduction["report"]).decode("utf-8")
    files["game/frontier/contact_sheet.ppm"]=postproduction["contact_sheet_ppm"]
    files["game/frontier/controller_latency.json"]=_json(measured_controller).decode("utf-8")
    files["game/frontier/advanced_navigation.json"]=_json(advanced_navigation).decode("utf-8")
    files["game/frontier/production_telemetry.json"]=_json(watchdog).decode("utf-8")
    files["game/frontier/seven_plane_assurance.json"]=_json(seven_axes).decode("utf-8")
    for audit_id,audit in sorted(seven_campaign_audits.items()):
        files["game/frontier/qa_seven/"+audit_id+".json"]=_json(audit).decode("utf-8")
    files["game/frontier/npcs.json"]=_json({
        "schema":"skeleton.game.original_npc_cast.v1",
        "world_digest":world.digest,
        "cast":npc_records,
        "native_npc_behaviors_verified":False,
    }).decode("utf-8")
    files["game/frontier/branch_playthroughs.json"]=_json(
        branch_proof
    ).decode("utf-8")
    files["game/frontier/learning_candidacy.json"]=_json({
        "schema":"skeleton.dragon.source_learning_candidacy.v1",
        "world_digest":world.digest,
        "dragon_report_receipt":dragon["receipt_digest"],
        "adversarial_receipt":dragon_review["receipt_digest"],
        "attack_receipt":dragon_attacks["receipt_digest"],
        "source_lessons":dragon["lessons"],
        "external_reviewer_signoff":False,
        "model_weights_changed":False,
    }).decode("utf-8")
    files["game/frontier/ecology_frame.json"]=_json(
        ecology_sample
    ).decode("utf-8")
    files["game/frontier/audio_mix.json"]=_json({
        "schema":"skeleton.game.adaptive_original_audio_resource.v1",
        "world_digest":world.digest,
        "score_digest":sound["score"].digest,
        "mix_receipt":mix["manifest"]["receipt_digest"],
        "rate":mix["manifest"]["sample_rate"],
        "pcm_base64":b64encode(mix["wav"][44:]).decode("ascii"),
    }).decode("utf-8")
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
        "world_assurance_receipt":world_assurance["receipt_digest"],
        "world_assurance_axes":world_assurance["axes_executed"],
        "story_digest":story.digest,
        "questbook_digest":questbook.digest,
        "storyboard_digest":storyboard.digest,
        "rig_digest":rig.digest,
        "foot_ik_receipt":ik["receipt_digest"],
        "ragdoll_receipt":ragdoll["receipt_digest"],
        "npc_supply_receipt":supply["snapshot_digest"],
        "cinematic_blocking_receipt":blocking["receipt_digest"],
        "controller_parity_receipt":parity["receipt_digest"],
        "soak_recovery_receipt":soak["receipt_digest"],
        "actual_hid_devices_qualified":0,
        "native_rgb_frames_captured_by_compiler":0,
        "elastic_skin_receipt":soft_skin["receipt_digest"],
        "npc_society_receipt":society["snapshot_digest"],
        "performance_receipt":performance["receipt_digest"],
        "dragon_visual_receipt":vision["receipt_digest"],
        "postproduction_receipt":postproduction["report"]["receipt_digest"],
        "native_postproduction_attested":False,
        "controller_latency_receipt":measured_controller["receipt_digest"],
        "production_watchdog_receipt":watchdog["snapshot_digest"],
        "seven_plane_assurance_receipt":seven_axes["receipt_digest"],
        "seven_campaign_audits_receipt":seven_campaign_audits["delivery"]["receipt_digest"],
        "advanced_navigation_receipt":advanced_navigation["assurance"]["receipt_digest"],
        "seven_campaign_source_checked":seven_campaign_audits["delivery"]["source_checks_passed"],
        "seven_plane_source_checks":seven_axes["passed"],
        "real_hardware_test_completed":False,
        "branch_plot_receipt":branch_proof["receipt_digest"],
        "full_branch_playthroughs":branch_proof["opening_branches_executed"],
        "different_endings_earned":branch_proof["distinct_endings_reached"],
        "npc_cast_count":len(npc_records),
        "npc_replay_receipts":[x["proof"]["snapshot_digest"] for x in npc_records],
        "ecology_receipt":ecology["receipt_digest"],
        "ecology_frame_receipt":ecology_sample["receipt_digest"],
        "adaptive_music_receipt":mix["manifest"]["receipt_digest"],
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
        "adaptive_music":mix,
        "plot_proof":branch_proof,
        "npcs":npc_records,"ecology":ecology,
        "rig":rig,"walk_cycle":walk_cycle,"elastic_skin":soft_skin,
        "ik":ik,"ragdoll":ragdoll,"supply":supply,"blocking":blocking,
        "controller_parity":parity,"soak":soak,
        "society":society,"performance":performance,
        "dragon_vision":vision,"postproduction":postproduction,
        "controller_qa":measured_controller,
        "production_watchdog":watchdog,"seven_plane_assurance":seven_axes,
        "seven_campaign_audits":seven_campaign_audits,
        "world_assurance":world_assurance,
        "advanced_navigation":advanced_navigation,
        "ecology_frame":ecology_sample,
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
            or compiled.get("adaptive_music")!=expected["adaptive_music"]
            or compiled.get("plot_proof")!=expected["plot_proof"]
            or compiled.get("ik")!=expected["ik"]
            or compiled.get("ragdoll")!=expected["ragdoll"]
            or compiled.get("supply")!=expected["supply"]
            or compiled.get("blocking")!=expected["blocking"]
            or compiled.get("controller_parity")!=expected["controller_parity"]
            or compiled.get("soak")!=expected["soak"]
            or compiled.get("rig")!=expected["rig"]
            or compiled.get("walk_cycle")!=expected["walk_cycle"]
            or compiled.get("elastic_skin")!=expected["elastic_skin"]
            or compiled.get("society")!=expected["society"]
            or compiled.get("performance")!=expected["performance"]
            or compiled.get("dragon_vision")!=expected["dragon_vision"]
            or compiled.get("postproduction")!=expected["postproduction"]
            or compiled.get("controller_qa")!=expected["controller_qa"]
            or compiled.get("production_watchdog")!=expected["production_watchdog"]
            or compiled.get("seven_plane_assurance")!=expected["seven_plane_assurance"]
            or compiled.get("seven_campaign_audits")!=expected["seven_campaign_audits"]
            or compiled.get("world_assurance")!=expected["world_assurance"]
            or compiled.get("advanced_navigation")!=expected["advanced_navigation"]
            or compiled.get("npcs")!=expected["npcs"]
            or compiled.get("ecology")!=expected["ecology"]
            or compiled.get("ecology_frame")!=expected["ecology_frame"]
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
