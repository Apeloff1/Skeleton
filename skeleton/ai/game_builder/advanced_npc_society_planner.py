"""Bounded AI civic director: directly witnessed, finite original societies.

No action claims society memory unless the actual NPC is physically nearby.
Every planned milestone is independently replayed from an authored source.
Finite search failures are INCONCLUSIVE, not proof the society cannot thrive.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import validate_advanced_scene
from .advanced_npc_society_runtime import (
    SocietyActionError,start,apply_scene,step,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.civic_story_plan.v1"
DEFAULT_MAX_ACTIONS=100


class CivicPlanningError(ValueError):
    """Invalid citizen budget or altered civic proof."""


def _digest(payload):
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _near(a,b):
    return abs(a[0]-b[0])+abs(a[1]-b[1])<=1


def plan_original_civic_milestone(scene,settings=None,*,max_actions=DEFAULT_MAX_ACTIONS,
                                 retire=False):
    if type(max_actions) is not int or not 1<=max_actions<=128:
        raise CivicPlanningError("finite exact citizen action budget required")
    if type(retire) is not bool:
        raise CivicPlanningError("source-bound retirement is a typed choice")
    doc=make_editor_document("npc_society",settings)
    rules=doc["settings"]
    source=validate_advanced_scene(scene,rules)
    if source["editor"]!="npc_society":
        raise CivicPlanningError("source must be original NPC society")
    state=start(rules,source["seed"])
    apply_scene(state,rules,source["layout"])
    commands=[]
    limitation=None

    def act(action):
        if len(commands)>=max_actions:
            raise SocietyActionError("bounded civic search ran out of actions")
        step(state,rules,action)
        commands.append(action)

    def move_to(position):
        guard=0
        while state["position"]!=position:
            guard+=1
            if guard>64:
                raise SocietyActionError("original civic route outside finite safe navigation")
            x,y=state["position"]
            tx,ty=position
            if x!=tx:act("east" if tx>x else "west")
            else:act("north" if ty>y else "south")

    try:
        for who in (0,1):
            if who>=state["embodied"]:
                raise SocietyActionError("two embodied independent witnesses required")
            act("focus:"+str(who))
            # Witnesses can move each social tick. A finite receding-horizon
            # director pursues current coordinates, then records direct sight.
            for _ in range(52):
                witness=state["residents"][who]
                if _near(state["position"],witness["position"]):
                    act("observe")
                    break
                x,y=state["position"]
                tx,ty=witness["position"]
                if x!=tx:act("east" if tx>x else "west")
                else:act("north" if ty>y else "south")
            else:
                raise SocietyActionError("moving witness not physically reachable in budget")
        move_to(state["sites"]["hall"])
        act("mediate")
        act("checkpoint")
        if retire:
            move_to(state["sites"]["home"])
            act("retire")
        if not state["community_checkpoint"] or (
            retire and not state["retired"]
        ):
            raise SocietyActionError("real two-witness civic contract not completed")
        proof=run_advanced_session("npc_society",rules,commands,
                                   seed=source["seed"],scene=source)
        if not proof["state"]["community_checkpoint"] or (
            retire and not proof["state"]["retired"]
        ) or verify_advanced_session(proof,rules) is not True:
            raise CivicPlanningError("civic milestone failed independent replay")
        actual=proof["state"]
        result={
            "schema":SCHEMA,"status":"replay_verified_civic_resolution",
            "source_digest":source["digest"],"settings_digest":doc["digest"],
            "actions":list(commands),"action_count":len(commands),
            "witnesses":[0,1],
            "retired":actual["retired"],
            "world_still_playable":not actual["finished"],
            "trust":actual["trust"],
            "lod":rules["simulation_lod"],
            "memory_receipts":len(actual["memories"]),
            "background_batches":actual["background_batches"],
            "replay_digest":proof["digest"],
            "max_actions":max_actions,"requested_retirement":retire,
            "independent_replay_verified":True,
            "exhaustive_search_proved":False,"native_hardware_verified":False,
            "publication_certified":False,
        }
        return {**result,"digest":_digest(result)}
    except SocietyActionError as exc:
        limitation=str(exc)
        result={
            "schema":SCHEMA,"status":"inconclusive_bounded_civic_search",
            "source_digest":source["digest"],"settings_digest":doc["digest"],
            "actions":[],"action_count":0,
            "best_partial_actions":list(commands),
            "best_partial_evidence":list(state["evidence"]),
            "best_partial_position":list(state["position"]),
            "limitation":limitation,
            "max_actions":max_actions,"requested_retirement":retire,
            "independent_replay_verified":False,
            "exhaustive_search_proved":False,"native_hardware_verified":False,
            "publication_certified":False,
        }
        return {**result,"digest":_digest(result)}


def verify_original_civic_plan(record,scene,settings=None):
    if type(record) is not dict or record.get("schema")!=SCHEMA:
        raise CivicPlanningError("exact original civic receipt required")
    fresh=plan_original_civic_milestone(
        scene,settings,max_actions=record.get("max_actions"),
        retire=record.get("requested_retirement"),
    )
    if fresh!=record:
        raise CivicPlanningError("civic evidence, action history or source was altered")
    return True


__all__=["SCHEMA","CivicPlanningError","plan_original_civic_milestone",
         "verify_original_civic_plan"]
