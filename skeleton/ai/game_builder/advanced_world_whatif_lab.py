"""Bounded adversarial what-if laboratory for replay-verified original worlds.

Only actual, separately authenticated physical/genre source events and original
NPC-world actions can enter a counterfactual. The lab explores bounded
adjacent reorderings, completely replays the ORIGINAL game sources and NPC
world for each alternative, and records how causality *actually* changed.

"Preferred" describes an explicit author-selected world metric, never a
claim that a model improved or that the simulated world is universally better.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from hashlib import sha256
import json

from .advanced_interleaved_world import (
    MAX_TIMELINE_ENTRIES,InterleavedWorldError,
    run_interleaved_world,verify_interleaved_world,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.adversarial_world_whatif.v1"
MAX_DEPTH=3
MAX_ATTEMPTS=48
MAX_ACCEPTED=16
MAX_REJECTED=32
OBJECTIVES=(
    "eyewitness_coverage",
    "community_recovery",
    "resource_stewardship",
    "quest_progress",
)
METRICS=(
    "quests_completed","quests_exploited","active_quests",
    "direct_memories","rumor_memories","rumor_edges",
    "site_integrity","site_stock","supplies","stamina",
    "reputation","gold","world_tick","total_npc_walks",
)


class WorldWhatIfError(ValueError):
    """A what-if scenario lacked genuine signed gameplay or finite custody."""


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def _summary(state):
    """Only original engine state, never authored desiderata."""
    quests=state["quests"]
    return {
        "quests_completed":state["quests_completed"],
        "quests_exploited":state["quests_exploited"],
        "active_quests":sum(q["status"]=="active" for q in quests),
        "direct_memories":sum(len(n["memories"]) for n in state["npcs"]),
        "rumor_memories":sum(len(n["heard"]) for n in state["npcs"]),
        "rumor_edges":len(state["rumor_edges"]),
        "site_integrity":sum(s["integrity"] for s in state["sites"]),
        "site_stock":sum(s["stock"] for s in state["sites"]),
        "supplies":state["supplies"],
        "stamina":state["stamina"],
        "reputation":state["reputation"],
        "gold":state["gold"],
        "world_tick":state["tick"],
        "total_npc_walks":state["npc_walks"],
    }


def _score(metrics,objective):
    if objective=="eyewitness_coverage":
        return (
            metrics["direct_memories"],metrics["quests_completed"],
            -metrics["quests_exploited"],metrics["site_integrity"],
        )
    if objective=="community_recovery":
        return (
            metrics["site_integrity"],metrics["quests_completed"],
            -metrics["quests_exploited"],metrics["site_stock"],
        )
    if objective=="resource_stewardship":
        return (
            metrics["site_stock"],metrics["supplies"],metrics["gold"],
            metrics["site_integrity"],
        )
    return (
        metrics["quests_completed"],-metrics["quests_exploited"],
        metrics["active_quests"],metrics["direct_memories"],
    )


def _evidence(proof):
    """Preserve source order and witness authority without inventing events."""
    return {
        "event_origin_order":[
            {
                "lane":row["lane"],
                "source_index":row["source_index"],
                "event_index":row["event_index"],
                "world_tick":row["world_tick"],
                "original_event_id":row["source"].get("world_event_id"),
                "original_witnesses":row["source"].get("direct_witnesses",[]),
                "causal_quests":row["source"].get("origin_quests",[]),
                "source_receipt":row["source"].get("source_receipt"),
            } for row in proof["timeline"]
        ],
        "final_world_digest":_hash(proof["world_state"]),
        "original_head_hash":proof["head_hash"],
    }


def _make_clock(original,identity,durations):
    tick=0
    result=[]
    for source_index in identity:
        step=deepcopy(original[source_index])
        step["at"]=tick
        result.append(step)
        tick+=durations[source_index]
    return result


def _validate_objective_and_budget(objective,max_depth,max_attempts,max_accepted):
    if (type(objective) is not str or objective not in OBJECTIVES or
        type(max_depth) is not int or not 1<=max_depth<=MAX_DEPTH or
        type(max_attempts) is not int or not 1<=max_attempts<=MAX_ATTEMPTS or
        type(max_accepted) is not int or not 1<=max_accepted<=MAX_ACCEPTED):
        raise WorldWhatIfError("typed objective and finite adversarial attempt budgets required")


def run_world_whatif(physical,genres,scene,timeline,settings=None,*,
                     objective="eyewitness_coverage",
                     max_depth=2,max_attempts=24,max_accepted=8):
    _validate_objective_and_budget(
        objective,max_depth,max_attempts,max_accepted)
    if type(timeline) not in (list,tuple) or not 2<=len(timeline)<=MAX_TIMELINE_ENTRIES:
        raise WorldWhatIfError("source-authenticated world requires at least two authored events")
    try:
        config=make_editor_document("quest_director",settings)["settings"]
        baseline=run_interleaved_world(physical,genres,scene,timeline,config)
        verify_interleaved_world(baseline,physical,genres,scene,timeline,config)
        source=deepcopy(list(timeline))
        durations=[
            receipt["world_tick"]-receipt["source_at"]
            for receipt in baseline["timeline"]
        ]
        if any(type(duration) is not int or duration<=0 for duration in durations):
            raise WorldWhatIfError("actual source event ticks must progress")
        metrics=_summary(baseline["world_state"])
        base_score=_score(metrics,objective)
        queue=deque([(tuple(range(len(source))),(),0)])
        visited={tuple(range(len(source)))}
        admitted=[]
        rejected=[]
        attempts=0
        # Breadth-first means shallow, cheaper, explainable world changes
        # are evaluated before deeper labyrinthine causal permutations.
        while queue and attempts<max_attempts and len(admitted)<max_accepted:
            order,path,depth=queue.popleft()
            if depth>=max_depth:
                continue
            for left in range(len(order)-1):
                swapped=list(order)
                a,b=swapped[left],swapped[left+1]
                # Swapping two events from the same original source risks
                # forging the internally witnessed source action order.
                ax,bx=source[a],source[b]
                if (ax["lane"]==bx["lane"] and
                    ax["lane"] in ("physical","genre") and
                    ax["source_index"]==bx["source_index"]):
                    continue
                swapped[left],swapped[left+1]=b,a
                sequence=tuple(swapped)
                if sequence in visited:
                    continue
                visited.add(sequence)
                changes=path+((left,left+1),)
                if attempts>=max_attempts:
                    break
                attempts+=1
                proposal=_make_clock(source,sequence,durations)
                scenario_id=_hash({"baseline":baseline["digest"],
                                   "original_order":sequence})
                try:
                    result=run_interleaved_world(
                        physical,genres,scene,proposal,config)
                    verify_interleaved_world(
                        result,physical,genres,scene,proposal,config)
                except (InterleavedWorldError,ValueError,KeyError,TypeError,
                        IndexError) as exc:
                    if len(rejected)<MAX_REJECTED:
                        rejected.append({
                            "scenario_id":scenario_id,
                            "swaps":[list(pair) for pair in changes],
                            "reason":"canonical_gameplay_or_source_order_rejected",
                            "error_type":type(exc).__name__,
                        })
                    continue
                alt_metrics=_summary(result["world_state"])
                score=_score(alt_metrics,objective)
                scenario={
                    "scenario_id":scenario_id,
                    "source_position_order":list(sequence),
                    "swaps":[list(pair) for pair in changes],
                    "depth":depth+1,
                    "timeline":proposal,
                    "campaign_digest":result["digest"],
                    "metrics":alt_metrics,
                    "delta_from_baseline":{
                        name:alt_metrics[name]-metrics[name]
                        for name in METRICS
                    },
                    "objective_score":list(score),
                    "outperforms_baseline_on_selected_objective":score>base_score,
                    "source_evidence":_evidence(result),
                    "actually_replayed":True,
                    "native_certification_claim":False,
                }
                admitted.append(scenario)
                # Only valid candidate histories may seed deeper changes.
                if depth+1<max_depth:
                    queue.append((sequence,changes,depth+1))
                if len(admitted)>=max_accepted:
                    break
        # Highest measured objective tuple first; identical merit has a
        # deterministic short-depth then source-hash tie breaker.
        ordered=sorted(
            admitted,key=lambda c:(tuple(-v for v in c["objective_score"]),
                                  c["depth"],c["scenario_id"]))
        chosen=ordered[0] if ordered else None
        report={
            "schema":SCHEMA,
            "objective":objective,
            "budget":{"max_depth":max_depth,"max_attempts":max_attempts,
                      "max_accepted":max_accepted},
            "source_world_scene_digest":scene["digest"],
            "baseline_campaign_digest":baseline["digest"],
            "baseline":{
                "timeline":source,
                "metrics":metrics,
                "objective_score":list(base_score),
                "source_evidence":_evidence(baseline),
            },
            "attempted_permutations":attempts,
            "accepted_scenarios":ordered,
            "rejected_scenarios":rejected,
            "accepted_count":len(ordered),
            "rejected_count":attempts-len(ordered),
            "selected_scenario_id":(
                chosen["scenario_id"] if chosen else None
            ),
            "selected_is_measurably_better_than_baseline":(
                chosen["outperforms_baseline_on_selected_objective"]
                if chosen else False
            ),
            "source_games_changed":False,
            "automatic_authoring_committed":False,
            "automatic_ai_weight_promotion":False,
            "hardware_certified":False,
        }
        return {**report,"digest":_hash(report)}
    except WorldWhatIfError:
        raise
    except (InterleavedWorldError,ValueError,TypeError,KeyError,IndexError) as exc:
        raise WorldWhatIfError(
            "original source replay or what-if baseline was not authenticated"
        ) from exc


def verify_world_whatif(proof,physical,genres,scene,timeline,settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise WorldWhatIfError("signed bounded what-if experiment proof required")
    try:
        budget=proof["budget"]
        result=run_world_whatif(
            physical,genres,scene,timeline,settings,
            objective=proof["objective"],
            max_depth=budget["max_depth"],
            max_attempts=budget["max_attempts"],
            max_accepted=budget["max_accepted"])
    except (KeyError,ValueError,TypeError,IndexError) as exc:
        raise WorldWhatIfError("forged what-if objective or resource budget") from exc
    if result!=proof:
        raise WorldWhatIfError(
            "alternative gameplay, NPC witness state or preferred outcome forged")
    return True


__all__=[
    "SCHEMA","MAX_DEPTH","MAX_ATTEMPTS","MAX_ACCEPTED","OBJECTIVES",
    "METRICS","WorldWhatIfError","run_world_whatif","verify_world_whatif",
]
