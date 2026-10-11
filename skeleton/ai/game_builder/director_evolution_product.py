"""Consumer source augmented by actually executed NPC, quest and scene systems.

Jeeves/Dragon-compatible handoff receipts are evidence of local modules, not
claims of provider permissions, learned models or publication certification.
The original canonical browser source is retained unchanged and separately
verified against all additional world components.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from .contracts import canonical_digest, canonical_json
from .quest_scene_engine import DirectorError, DirectorWorld
from .quest_director_solver import solve_quest
from .quest_director_enhanced_product import build_earned_story_product
from .quest_director_studio import DirectorStudioProduct
from .modular_director_session import simulate_director, orchestrator_plan
from .modular_mission_compiler import compile_modular_missions
from .npc_social_economy import (
    new_economy, produce_goods, diffuse_witnessed_memory, citizen_dialogue,
)
from .quest_pareto_planner import (
    PlannerBudget, PlannerError, find_quest_routes,
)
from .director_capability_graph import TIERS
from .modular_scene_compositor import compose_scene, storyboard
from .npc_authoring import read_npc_roster


def _payload(obj):
    return (canonical_json(obj)+"\n").encode("utf-8")


def build_evolution_product(
    world: DirectorWorld, *,
    population: int = 96,
    tier: str = "desktop",
    deep_route_search: bool = True,
    mirror_attempts: int = 128,
    npc_blueprint: str | None = None,
    npc_human_reviewed: bool = False,
    authorized: bool,
) -> DirectorStudioProduct:
    if not authorized:
        raise PermissionError("original consumer product and agent society need authorization")
    if not isinstance(world,DirectorWorld):
        raise DirectorError("typed original designed game required")
    if tier not in TIERS or type(population) is not int or not 3<=population<=512:
        raise DirectorError("unknown hardware tier or actual population budget")
    if type(deep_route_search) is not bool:
        raise DirectorError("deep route exploration must be explicitly enabled")
    if (npc_blueprint is None and npc_human_reviewed) or (
        npc_blueprint is not None and npc_human_reviewed is not True
    ):
        raise DirectorError("custom original NPCs need both source and human review")
    approved=(read_npc_roster(world,npc_blueprint,human_reviewed=True,
                              authorized=True) if npc_blueprint is not None else None)
    base=build_earned_story_product(
        world,authorized=True,mirror_attempts=mirror_attempts,
    )
    main=next(q for q in world.quests if q.scope=="main")
    proof=solve_quest(world,main.key,strategy="creative",authorized=True)
    session=simulate_director(
        world,proof.replay.actions,population=population,
        tier=tier,authorized=True,
        authored_society=approved.society if approved is not None else None,
    )
    missions=compile_modular_missions(world,authorized=True)
    capability=orchestrator_plan(tier)
    society=session.session.society
    # Independent local material economy; profession stock and dialogue
    # derived from the exact final NPC schedules and original event history.
    market=produce_goods(new_economy(society,authorized=True),
                         society,authorized=True)
    rumored=diffuse_witnessed_memory(
        society,subject="hero",max_recipients=min(32,population),
        authorized=True,
    )
    sample=tuple(citizen_dialogue(rumored,p.key) for p in rumored.profiles[:12])
    if session.session.story!=proof.replay.final:
        raise DirectorError("evolution product narrative replay differs from original")
    if session.session.missions.book_digest!=missions.digest:
        raise DirectorError("modular mission provenance lost during packaging")
    plan=None
    if deep_route_search:
        plan=find_quest_routes(
            world,main.key,objective="balanced",
            budget=PlannerBudget(max_expansions=800,max_actions=120,
                                 beam=12,minimum_diversity=2),
            authorized=True,
        )
        if not plan.routes:
            raise DirectorError("replayable alternate mission plans not available")
    files=dict(base.files)
    files.pop("release.json")
    if approved is not None:
        files["systems/npc_authoring_handoff.json"]=_payload(approved.evidence())
    files["systems/capability_graph.json"]=_payload(capability.payload())
    files["systems/npc_society_replay.json"]=_payload(session.payload())
    files["systems/npc_economy.json"]=_payload(market.payload())
    files["systems/npc_social_propagation.json"]=_payload({
        "schema":"skeleton.game_builder.npc_epistemic_review.v1",
        "source_society_digest":society.digest,
        "rumor_society_digest":rumored.digest,
        "citizens":len(rumored.minds),
        "citizens_with_memories":sum(bool(m.memories) for m in rumored.minds),
        "citizens_with_rumor_memories":sum(
            any(memory.origin=="rumor" for memory in m.memories) for m in rumored.minds),
        "dialogue_samples":list(sample),
        "provider_language_model_invoked":False,
    })
    frames=[
        compose_scene(world,society,s.key,tier=tier,authorized=True).payload()
        for s in world.scenes
    ]
    cinematic_witnesses=[]
    for scene in world.scenes:
        for cutscene in scene.cutscenes:
            if len(cinematic_witnesses)>=16:
                break
            series=storyboard(world,society,scene.key,cutscene.key,
                              tier=tier,authorized=True)
            cinematic_witnesses.append({
                "scene":scene.key,"cutscene":cutscene.key,
                "sample_times":[frame.at_ms for frame in series],
                "frame_digests":[frame.digest for frame in series],
                "last_frame":series[-1].payload(),
            })
        if len(cinematic_witnesses)>=16:
            break
    files["systems/original_scene_frames.json"]=_payload({
        "schema":"skeleton.game_builder.original_modular_scene_frames.v1",
        "world_digest":world.digest,"tier":tier,
        "sampled_scene_frames":frames,
        "sampled_cinematic_storyboards":cinematic_witnesses,
        "native_cinematic_renderer_verified":False,
        "authored_audio_playback_verified":False,
    })
    files["systems/modular_missions.json"]=_payload(missions.payload())
    files["systems/quest_routes.json"]=_payload(
        plan.payload() if plan else {
            "schema":"skeleton.game_builder.route_planning_deferred.v1",
            "reason":"explicitly_disabled_by_operator",
        }
    )
    files["almanac/evolution_engine_evidence.json"]=_payload({
        "schema":"skeleton.game_builder.evolution_engine_almanac.v1",
        "world_digest":world.digest,
        "canonical_replay_digest":proof.replay.digest,
        "integrated_replay_digest":session.digest,
        "mission_book_digest":missions.digest,
        "capability_plan_digest":capability.digest,
        "market_digest":market.digest,
        "npc_society_digest":society.digest,
        "npc_rumor_digest":rumored.digest,
        "route_search_digest":plan.digest if plan else None,
        "actor_simulation":session.performance,
        "actual_authored_scene_count":len(world.scenes),
        "actual_quest_count":len(world.quests),
        "full_original_scene_playback":False,
        "verified_native_scene_runtime":False,
        "trained_model_weights":False,
        "game_quality_human_evaluated":False,
        "publication_authorized":False,
    })
    if sum(len(x) for x in files.values())>12_000_000:
        raise DirectorError("expanded original game source exceeds bounded package budget")
    manifest={
        **{k:v for k,v in base.manifest.items() if k not in {
            "manifest_digest","files"
        }},
        "schema":"skeleton.game_builder.evolution_source_release.v1",
        "modular_missions":missions.digest,
        "society_runtime":society.digest,
        "society_population":population,
        "target_tier":tier,
        "integration_evidence":session.digest,
        "deep_route_search":bool(plan),
        "consumer_publication_authorized":False,
        "files":{name:sha256(data).hexdigest()
                 for name,data in sorted(files.items())},
    }
    manifest["manifest_digest"]=canonical_digest(manifest)
    files["release.json"]=_payload(manifest)
    return replace(base,files=files,manifest=manifest)


__all__=["build_evolution_product"]
