"""AI-facing coach for original, replay-verifiable sporting matches.

The planner explores only transitions produced by the same deterministic,
bounded sports engine used by players. It may propose original strategy but
cannot mint points, skip defenders, evade action points or declare native
hardware certification. Beam exhaustion remains INCONCLUSIVE, never proof of
an impossible match or a promise of unwitnessed victory.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .advanced_gameplay_runtime import (
    MAX_TURNS, run_advanced_session, verify_advanced_session,
)
from .advanced_level_scenes import validate_advanced_scene
from .advanced_sports_runtime import (
    SportsActionError, start, step, apply_scene,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.original_sports_coach.v1"
DEFAULT_MAX_STATES=16000
DEFAULT_BEAM_WIDTH=48
COACH_ACTIONS={
    "team":("shoot","sprint","advance","dribble","pass","cross",
            "intercept","tactic:press","tactic:hold","rest"),
    "racket":("serve","smash","drive","net","slice","lob","rest"),
    "arena":("score","dash","carry","throw","sidestep",
             "tackle","guard","rest"),
    "turn_based":("shoot","dash","move","end_turn","switch_lane",
                  "pass","tackle","rest"),
}


class SportsPlanningError(ValueError):
    """Bad source, unsupported budget or falsified original match receipt."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _signature(s):
    return (
        s["mode"],s["tick"],tuple(s["home"]),tuple(s["away"]),
        tuple(s["teammate"]),tuple(s["ball"]),s["owner"],
        s["home_score"],s["away_score"],s["stamina"],s["away_stamina"],
        s["fatigue"],s["subs_left"],s["ap_remaining"],s["turns_committed"],
        s["rally"],s["rally_strokes"],s["opponent_readiness"],s["tempo"],
        s["passes"],s["shots"],s["interceptions"],s["finished"],
    )


def _quality(s,actions):
    goal_progress=s["home"][0]*10 if s["mode"]!="racket" else s["rally_strokes"]*15
    possession=100 if s["owner"]=="home" or s["mode"]=="racket" else 0
    return (
        s["home_score"]*20000-s["away_score"]*22000+
        goal_progress+possession+s["stamina"]+
        (s["ap_remaining"]*4 if s["mode"]=="turn_based" else 0)-
        len(actions)*12-s["fatigue"]
    )


def plan_original_sports_match(scene,settings=None,*,max_states=DEFAULT_MAX_STATES,
                               max_depth=64,beam_width=DEFAULT_BEAM_WIDTH):
    for name,value,minimum,maximum in (
        ("max_states",max_states,8,50000),
        ("max_depth",max_depth,1,MAX_TURNS),
        ("beam_width",beam_width,1,256),
    ):
        if type(value) is not int or not minimum<=value<=maximum:
            raise SportsPlanningError("invalid original sports search "+name)
    configuration=make_editor_document("sports",settings)
    rules=configuration["settings"]
    source=validate_advanced_scene(scene,rules)
    if source["editor"]!="sports":
        raise SportsPlanningError("signed original sports scene required")
    model=rules["rules"]
    available=COACH_ACTIONS[model]
    initial=start(rules,source["seed"])
    apply_scene(initial,rules,source["layout"])
    frontier=[(initial,tuple())]
    seen={_signature(initial)}
    expanded=0
    depth_reached=0
    pruned=False
    hit_limit=False
    best=(initial,tuple())

    def proved(actions):
        session=run_advanced_session("sports",rules,list(actions),
                                     seed=source["seed"],scene=source)
        real=session["state"]
        if not real["finished"] or not real["victory"] or (
            real["home_score"]<=real["away_score"]
        ):
            raise SportsPlanningError("winning sports strategy failed physical replay")
        if verify_advanced_session(session,rules) is not True:
            raise SportsPlanningError("independent sports match verification failed")
        body={
            "schema":SCHEMA,"status":"replay_verified_win",
            "rules":model,"source_digest":source["digest"],
            "settings_digest":configuration["digest"],
            "actions":list(actions),"action_count":len(actions),
            "final_home_score":real["home_score"],
            "final_away_score":real["away_score"],
            "final_match_tick":real["tick"],
            "original_replay_digest":session["digest"],
            "expanded_transitions":expanded,
            "seen_physical_states":len(seen),
            "max_states":max_states,"max_depth":max_depth,
            "beam_width":beam_width,
            "independently_verified":True,
            "exhaustive_search_proved":False,
            "native_hardware_certified":False,
            "publication_certified":False,
        }
        return {**body,"digest":_digest(body)}

    for depth in range(max_depth):
        depth_reached=depth+1
        candidates=[]
        for physical,path in frontier:
            if physical["finished"] and physical["victory"]:
                return proved(path)
            for action in available:
                if expanded>=max_states:
                    hit_limit=True
                    break
                successor=deepcopy(physical)
                expanded+=1
                try:
                    step(successor,rules,action)
                except SportsActionError:
                    continue
                if successor["finished"]:
                    if successor["victory"]:
                        return proved(path+(action,))
                    continue
                signature=_signature(successor)
                if signature in seen:
                    continue
                seen.add(signature)
                next_actions=path+(action,)
                candidates.append((successor,next_actions))
                if _quality(successor,next_actions)>_quality(best[0],best[1]):
                    best=(successor,next_actions)
            if hit_limit:
                break
        if not candidates:
            break
        candidates.sort(
            key=lambda item:(_quality(item[0],item[1]),-len(item[1]),
                             item[1]),
            reverse=True,
        )
        if len(candidates)>beam_width:
            pruned=True
        frontier=candidates[:beam_width]
        if hit_limit:
            break

    # Exhaustion of a heuristic or a finite budget does not establish that
    # a game design is unwinnable, unfair or otherwise irreparable.
    body={
        "schema":SCHEMA,"status":"inconclusive_search_budget",
        "rules":model,"source_digest":source["digest"],
        "settings_digest":configuration["digest"],
        "actions":[],"action_count":0,
        "best_observed_actions":list(best[1]),
        "best_observed_home_score":best[0]["home_score"],
        "best_observed_away_score":best[0]["away_score"],
        "best_observed_position":list(best[0]["home"]),
        "expanded_transitions":expanded,
        "seen_physical_states":len(seen),
        "max_states":max_states,"max_depth":max_depth,
        "beam_width":beam_width,"depth_reached":depth_reached,
        "budget_reached":hit_limit,"beam_pruned":pruned,
        "independently_verified":False,
        "exhaustive_search_proved":False,
        "native_hardware_certified":False,
        "publication_certified":False,
    }
    return {**body,"digest":_digest(body)}


def verify_original_sports_plan(receipt,scene,settings=None):
    """Deterministically re-search the original field and recheck any winning replay."""
    if type(receipt) is not dict or receipt.get("schema")!=SCHEMA:
        raise SportsPlanningError("exact original sports coach receipt required")
    recomputed=plan_original_sports_match(
        scene,settings,
        max_states=receipt.get("max_states"),
        max_depth=receipt.get("max_depth"),
        beam_width=receipt.get("beam_width"),
    )
    if recomputed!=receipt:
        raise SportsPlanningError("sports planner output, limits or evidence were altered")
    return True


__all__=[
    "SCHEMA","COACH_ACTIONS","SportsPlanningError",
    "plan_original_sports_match","verify_original_sports_plan",
]
