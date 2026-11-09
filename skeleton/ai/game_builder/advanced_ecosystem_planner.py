"""Bounded AI habitat director using actual deterministic food-web transitions.

Only two spatial surveys, finite ecological interventions and a real living
population produce a checkpoint. Replays certify actions; they do not certify
biological science, native hardware or the impossibility of other worlds.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_gameplay_runtime import run_advanced_session,verify_advanced_session
from .advanced_level_scenes import validate_advanced_scene
from .advanced_ecosystem_runtime import EcosystemActionError,start,apply_scene,step
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.ecological_recovery_plan.v1"


class EcologyPlanningError(ValueError):
    """Invalid original conservation plan, finite budget or evidence."""


def _digest(payload):
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def plan_original_ecology(scene,settings=None,*,max_actions=100,retire=False):
    if type(max_actions) is not int or not 1<=max_actions<=128:
        raise EcologyPlanningError("conservation planner action budget must be bounded")
    if type(retire) is not bool:
        raise EcologyPlanningError("source-bound retirement must be a boolean")
    doc=make_editor_document("ecosystem",settings)
    rules=doc["settings"]
    scene=validate_advanced_scene(scene,rules)
    if scene["editor"]!="ecosystem":
        raise EcologyPlanningError("exact original living ecosystem required")
    state=start(rules,scene["seed"])
    apply_scene(state,rules,scene["layout"])
    commands=[]

    def act(command):
        if len(commands)>=max_actions:
            raise EcosystemActionError("source ecology planning budget exhausted")
        step(state,rules,command)
        commands.append(command)

    try:
        act("survey")
        # Spend only real resources; the director cannot claim restoration by
        # toggling environment flags or overriding ecological population.
        for _ in range(rules["minimum_interventions"]):
            habitat=state["habitats"][state["position"][0]+2*state["position"][1]]
            if state["seed_bank"]>=rules["seed_cost"] and (
                habitat["food"]+rules["plant_food"]<=habitat["capacity"]
            ):
                act("plant")
            elif state["credits"]>=rules["restoration_cost"]:
                act("restore")
            elif state["water"]>=rules["water_cost"]:
                act("water")
            else:
                raise EcosystemActionError("finite ecological interventions exhausted")
        act("east")
        act("north")
        act("survey")
        act("checkpoint")
        if retire:
            act("west")
            act("south")
            act("retire")
        if not state["conservation_checkpoint"] or (retire and not state["retired"]):
            raise EcosystemActionError("conservation proof was not earned by active world")
        game=run_advanced_session(
            "ecosystem",rules,commands,seed=scene["seed"],scene=scene
        )
        if not game["state"]["conservation_checkpoint"] or (
            retire and not game["state"]["retired"]
        ) or verify_advanced_session(game,rules) is not True:
            raise EcologyPlanningError("actual ecology replay did not prove milestone")
        result={
            "schema":SCHEMA,"status":"replay_verified_conservation",
            "source_digest":scene["digest"],"settings_digest":doc["digest"],
            "actions":list(commands),"action_count":len(commands),
            "surveys":list(game["state"]["surveys"]),
            "live_population":sum(x["population"] for x in game["state"]["species"]),
            "migrations":game["state"]["migration_events"],
            "predation_events":game["state"]["predation_events"],
            "world_still_playable":not game["state"]["finished"],
            "retired":game["state"]["retired"],
            "replay_digest":game["digest"],
            "max_actions":max_actions,"requested_retirement":retire,
            "independent_replay_verified":True,
            "exhaustive_search_proved":False,"native_hardware_verified":False,
            "publication_certified":False,
        }
        return {**result,"digest":_digest(result)}
    except EcosystemActionError as exc:
        result={
            "schema":SCHEMA,"status":"inconclusive_bounded_ecology",
            "source_digest":scene["digest"],"settings_digest":doc["digest"],
            "actions":[],"action_count":0,
            "best_partial_actions":list(commands),
            "best_partial_surveys":list(state["surveys"]),
            "best_partial_interventions":state["interventions"],
            "limitation":str(exc),
            "max_actions":max_actions,"requested_retirement":retire,
            "independent_replay_verified":False,
            "exhaustive_search_proved":False,"native_hardware_verified":False,
            "publication_certified":False,
        }
        return {**result,"digest":_digest(result)}


def verify_original_ecology_plan(record,scene,settings=None):
    if type(record) is not dict or record.get("schema")!=SCHEMA:
        raise EcologyPlanningError("exact original ecosystem receipt required")
    rebuilt=plan_original_ecology(
        scene,settings,max_actions=record.get("max_actions"),
        retire=record.get("requested_retirement"),
    )
    if rebuilt!=record:
        raise EcologyPlanningError("original ecology source, steps or proof was forged")
    return True


__all__=["SCHEMA","EcologyPlanningError","plan_original_ecology",
         "verify_original_ecology_plan"]
