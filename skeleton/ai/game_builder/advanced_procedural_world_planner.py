"""Proof-carrying AI exploration for nonterminal seeded original worlds.

This planner deliberately proves an earned landmark checkpoint, not a fictional
win condition for Minecraft-like worlds. The actual world generator, chunk
streamer, finite energy, persistent edits and replay are authoritative.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_gameplay_runtime import (
    AdvancedRuntimeError,run_advanced_session,verify_advanced_session,
)
from .advanced_level_scenes import validate_advanced_scene
from .advanced_procedural_world_runtime import (
    ProceduralWorldActionError,start,apply_scene,step,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.frontier_exploration_plan.v1"


class FrontierPlanningError(ValueError):
    """Original frontier plan violated source custody or evidence identity."""


def _digest(data):
    return sha256(json.dumps(data,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def plan_original_frontier(scene,settings=None,*,max_actions=100,retire=False):
    if type(max_actions) is not int or not 1<=max_actions<=128:
        raise FrontierPlanningError("original world plan must be bounded to replay turns")
    if type(retire) is not bool:
        raise FrontierPlanningError("retirement is an explicit typed decision")
    doc=make_editor_document("procedural_world",settings)
    rules=doc["settings"]
    src=validate_advanced_scene(scene,rules)
    if src["editor"]!="procedural_world":
        raise FrontierPlanningError("only a reviewed original frontier may be explored")
    state=start(rules,src["seed"])
    apply_scene(state,rules,src["layout"])
    commands=[]
    reason=None

    def move(target):
        x,y=state["position"]
        tx,ty=target
        for action,count in (
            ("east",max(0,tx-x)),("west",max(0,x-tx)),
            ("north",max(0,ty-y)),("south",max(0,y-ty)),
        ):
            for _ in range(count):
                perform(action)

    def perform(command):
        nonlocal reason
        if len(commands)>=max_actions:
            raise ProceduralWorldActionError("original finite plan action budget")
        if state["energy"]<=3 and state["inventory"]["food"]>0:
            # The recovery itself is source-owned and costs finite food.
            if command!="rest":
                if len(commands)>=max_actions-1:
                    raise ProceduralWorldActionError("no room for finite rest")
                step(state,rules,"rest")
                commands.append("rest")
        if state["thirst"]>=rules["thirst_limit"]-3 and state["inventory"]["water"]>0:
            if command!="drink":
                if len(commands)>=max_actions-1:
                    raise ProceduralWorldActionError("no room for finite hydration")
                step(state,rules,"drink")
                commands.append("drink")
        step(state,rules,command)
        commands.append(command)

    try:
        for landmark in state["landmarks"]:
            move(landmark["at"])
            perform("survey")
        perform("checkpoint")
        if retire:
            move([0,0])
            perform("retire")
        if not state["expedition_complete"] or (
            retire and not state["retired"]
        ):
            raise ProceduralWorldActionError("original exploration checkpoint was not earned")
        proof=run_advanced_session(
            "procedural_world",rules,commands,
            seed=src["seed"],scene=src,
        )
        if not proof["state"]["expedition_complete"] or (
            retire and not proof["state"]["retired"]
        ) or verify_advanced_session(proof,rules) is not True:
            raise FrontierPlanningError("original frontier could not replay its evidence")
        body={
            "schema":SCHEMA,"status":"replay_verified_expedition",
            "source_digest":src["digest"],"settings_digest":doc["digest"],
            "actions":list(commands),"action_count":len(commands),
            "landmarks_surveyed":list(proof["state"]["surveyed"]),
            "chunk_loads":proof["state"]["chunk_loads"],
            "residency_peak_cap":rules["active_chunks"],
            "persistent_changes":len(proof["state"]["persisted"]),
            "world_still_playable":not proof["state"]["finished"],
            "retired":proof["state"]["retired"],
            "replay_digest":proof["digest"],
            "max_actions":max_actions,"requested_retirement":retire,
            "independent_replay_verified":True,
            "exhaustive_search_proved":False,
            "native_hardware_verified":False,"publication_certified":False,
        }
        return {**body,"digest":_digest(body)}
    except ProceduralWorldActionError as exc:
        body={
            "schema":SCHEMA,"status":"inconclusive_bounded_exploration",
            "source_digest":src["digest"],"settings_digest":doc["digest"],
            "actions":[],"action_count":0,
            "best_partial_actions":list(commands),
            "best_partial_position":list(state["position"]),
            "landmarks_surveyed":list(state["surveyed"]),
            "limitation":str(exc),
            "max_actions":max_actions,"requested_retirement":retire,
            "independent_replay_verified":False,
            "exhaustive_search_proved":False,
            "native_hardware_verified":False,"publication_certified":False,
        }
        return {**body,"digest":_digest(body)}


def verify_original_frontier_plan(receipt,scene,settings=None):
    if type(receipt) is not dict or receipt.get("schema")!=SCHEMA:
        raise FrontierPlanningError("exact original frontier evidence is required")
    actual=plan_original_frontier(
        scene,settings,max_actions=receipt.get("max_actions"),
        retire=receipt.get("requested_retirement"),
    )
    if actual!=receipt:
        raise FrontierPlanningError("frontier plan or replay proof is not original")
    return True


__all__=["SCHEMA","FrontierPlanningError","plan_original_frontier",
         "verify_original_frontier_plan"]
