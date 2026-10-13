"""Bounded adversarial counterfactual laboratory for ORIGINAL game-world events.

A counterfactual is NOT synthetic training truth. It is a complete independent
execution of the same immutable game sources and world scene under another
authored admission order. Witness memories, quests and resource deltas come
only from canonical world execution, never a heuristic simulator.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .advanced_interleaved_world import (
    InterleavedWorldError,MAX_TIMELINE_ENTRIES,
    run_interleaved_world,verify_interleaved_world,
)

SCHEMA="skeleton.game_builder.world_counterfactual_laboratory.v1"
MAX_CANDIDATES=10
MAX_SOURCE_EVENTS=16
OBJECTIVES=(
    "preserve_sites","retain_supplies","maximize_earned_quests",
    "maximize_firsthand_memories",
)


class CounterfactualError(ValueError):
    """Counterfactual world, scenario or independent source replay invalid."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def _normalize_timeline(sequence):
    if type(sequence) not in (list,tuple) or not 1<=len(sequence)<=MAX_TIMELINE_ENTRIES:
        raise CounterfactualError("one to 96 original world clock entries required")
    normalized=[]
    for i,entry in enumerate(sequence):
        if type(entry) is not dict or set(entry) not in (
            {"at","lane","source_index","event_index"},{"at","lane","action"}):
            raise CounterfactualError("counterfactual requires exact authored source clock records")
        if type(entry["at"]) is not int or entry["at"]!=i:
            raise CounterfactualError("counterfactual clock must use contiguous canonical ticks")
        normalized.append(deepcopy(entry))
    return normalized


def derive_counterfactuals(timeline,limit=6):
    """Stable adjacent swaps: same source actions, no cloned/missing achievements."""
    if type(limit) is not int or not 1<=limit<=MAX_CANDIDATES:
        raise CounterfactualError("candidate derivation limit must be 1 to 10")
    original=_normalize_timeline(timeline)
    proposals=[]
    seen={_digest(original)}
    for index in range(len(original)-1):
        a,b=original[index],original[index+1]
        if a["lane"]=="world" and b["lane"]=="world":
            continue
        if (a["lane"]==b["lane"] and a["lane"]!="world" and
            a["source_index"]==b["source_index"]):
            # Preserve original session event order even in a hypothetical.
            continue
        other=deepcopy(original)
        other[index],other[index+1]=other[index+1],other[index]
        other[index]["at"]=index
        other[index+1]["at"]=index+1
        digest=_digest(other)
        if digest in seen:
            continue
        seen.add(digest)
        proposals.append({
            "id":"adjacent_%02d_%02d"%(index,index+1),
            "timeline":other,
        })
        if len(proposals)==limit:
            break
    return proposals


def _measure(proof):
    state=proof["world_state"]
    quests=state["quests"]
    npcs=state["npcs"]
    sites=state["sites"]
    direct=sum(len(npc["memories"]) for npc in npcs)
    return {
        "clock_ticks":state["tick"],
        "world_turns":state["turn"],
        "player_supplies":state["supplies"],
        "player_stamina":state["stamina"],
        "player_gold":state["gold"],
        "player_reputation":state["reputation"],
        "site_integrity":[site["integrity"] for site in sites],
        "site_stock":[site["stock"] for site in sites],
        "total_site_integrity":sum(site["integrity"] for site in sites),
        "total_site_stock":sum(site["stock"] for site in sites),
        "quests_started":len(quests),
        "quests_completed":state["quests_completed"],
        "quests_exploited":state["quests_exploited"],
        "active_quests":sum(q["status"]=="active" for q in quests),
        "expired_quests":sum(q["status"]=="expired" for q in quests),
        "firsthand_memory_records":direct,
        "rumor_edges":len(state["rumor_edges"]),
        "direct_witness_counts":[len(npc["memories"]) for npc in npcs],
        "physical_causes":sum(x["actor"]=="external:physics"
                              for x in state["events_log"]),
        "genre_causes":sum(x["actor"]=="external:genre"
                           for x in state["events_log"]),
        "source_actor_chronology":[x["actor"] for x in state["events_log"]],
    }


def _delta(base,current):
    keys=(
        "clock_ticks","world_turns","player_supplies","player_stamina",
        "player_gold","player_reputation","total_site_integrity",
        "total_site_stock","quests_started","quests_completed",
        "quests_exploited","active_quests","expired_quests",
        "firsthand_memory_records","rumor_edges",
        "physical_causes","genre_causes",
    )
    deltas={key:current[key]-base[key] for key in keys}
    deltas["site_integrity"]=[a-b for a,b in zip(
        current["site_integrity"],base["site_integrity"])]
    deltas["site_stock"]=[a-b for a,b in zip(
        current["site_stock"],base["site_stock"])]
    deltas["direct_witness_counts"]=[a-b for a,b in zip(
        current["direct_witness_counts"],base["direct_witness_counts"])]
    deltas["source_actor_order_changed"]=(
        current["source_actor_chronology"]!=base["source_actor_chronology"])
    return deltas


def _score(metrics,objective):
    return {
        "preserve_sites":metrics["total_site_integrity"],
        "retain_supplies":metrics["player_supplies"],
        "maximize_earned_quests":metrics["quests_completed"],
        "maximize_firsthand_memories":metrics["firsthand_memory_records"],
    }[objective]


def run_counterfactual_laboratory(physical,genres,world_scene,baseline,
                                   cases,settings=None,*,
                                   objective="preserve_sites"):
    if objective not in OBJECTIVES or type(objective) is not str:
        raise CounterfactualError("reviewed measurable original-world objective required")
    if type(cases) not in (list,tuple) or not 1<=len(cases)<=MAX_CANDIDATES:
        raise CounterfactualError("one to ten independently executed scenarios required")
    baseline=_normalize_timeline(baseline)
    try:
        origin=run_interleaved_world(physical,genres,world_scene,baseline,settings)
        verify_interleaved_world(origin,physical,genres,world_scene,baseline,settings)
    except (ValueError,KeyError,TypeError) as exc:
        raise CounterfactualError("original game baseline must independently replay") from exc
    baseline_metrics=_measure(origin)
    ledger=[]
    seen={_digest(baseline)}
    previous=_digest({
        "schema":SCHEMA,"origin":origin["digest"],"objective":objective
    })
    candidates=[]
    for position,case in enumerate(cases):
        if (type(case) is not dict or set(case)!={"id","timeline"} or
            type(case["id"]) is not str or not 1<=len(case["id"])<=48 or
            any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in case["id"]) or
            case["id"] in {r["id"] for r in ledger}):
            raise CounterfactualError("unique safe scenario identifier and exact source clock required")
        sequence=_normalize_timeline(case["timeline"])
        key=_digest(sequence)
        if key in seen:
            raise CounterfactualError("identical or repeated what-if clock is not another experiment")
        seen.add(key)
        status="valid"
        metrics=None
        difference=None
        actual_digest=None
        reason=None
        try:
            independent=run_interleaved_world(
                physical,genres,world_scene,sequence,settings)
            verify_interleaved_world(
                independent,physical,genres,world_scene,sequence,settings)
            # Objective scores are NEVER used to invent physical outcomes.
            metrics=_measure(independent)
            difference=_delta(baseline_metrics,metrics)
            actual_digest=independent["digest"]
            candidates.append((case["id"],metrics))
        except InterleavedWorldError as exc:
            status="rejected_by_original_game_rules"
            reason=str(exc)
        record={
            "id":case["id"],"scenario_index":position,
            "timeline":sequence,"timeline_digest":key,
            "status":status,"reason":reason,
            "actual_world_digest":actual_digest,
            "measured_world":metrics,"difference_from_baseline":difference,
            "measured_score":_score(metrics,objective) if metrics else None,
        }
        head=_digest({"previous":previous,"record":record})
        ledger.append({**record,"previous_hash":previous,"head_hash":head})
        previous=head
    ranked=[("baseline",baseline_metrics)]+candidates
    # Stable tie-break prefers the unchanged baseline, avoiding unwarranted
    # automated churn. This is an authored metric preference, not a claim
    # about game quality or autonomous release authorization.
    highest=max(_score(m,objective) for _,m in ranked)
    selected=next(name for name,m in ranked if _score(m,objective)==highest)
    payload={
        "schema":SCHEMA,"objective":objective,
        "baseline_world_digest":origin["digest"],
        "baseline_timeline_digest":_digest(baseline),
        "baseline_world":baseline_metrics,
        "baseline_score":_score(baseline_metrics,objective),
        "experiments":ledger,"candidate_count":len(ledger),
        "valid_count":len(candidates),
        "rejected_count":len(ledger)-len(candidates),
        "highest_measured_score":highest,
        "objective_favorite":selected,
        "head_hash":previous,
        "original_game_files_changed":False,
        "automatic_world_promotion_approved":False,
        "native_full_genre_certification":False,
    }
    return {**payload,"digest":_digest(payload)}


def verify_counterfactual_laboratory(proof,physical,genres,scene,baseline,
                                     cases,settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise CounterfactualError("source-replayed counterfactual evidence missing")
    replay=run_counterfactual_laboratory(
        physical,genres,scene,baseline,cases,settings,objective=proof["objective"])
    if replay!=proof:
        raise CounterfactualError("counterfactual metrics, witnesses or scores were forged")
    return True


__all__=["SCHEMA","MAX_CANDIDATES","OBJECTIVES","CounterfactualError",
         "derive_counterfactuals","run_counterfactual_laboratory",
         "verify_counterfactual_laboratory"]
