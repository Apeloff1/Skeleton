"""Adversarial cross-context NPC world robustness with fully replayed originals.

A preferred event order is NOT generalized from a single scene. Every reviewed
alternate is independently run on each separately signed authored NPC world
(climate, day phase, NPC geometry, sight). Only a schedule that succeeds in ALL
contexts is eligible; measurements are source-factual, not model predictions.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_interleaved_world import (
    InterleavedWorldError,run_interleaved_world,verify_interleaved_world,
)
from .advanced_world_whatif_lab import (
    WorldWhatIfError,verify_world_whatif,_summary,_score,OBJECTIVES,METRICS,
)
from .advanced_level_scenes import validate_advanced_scene
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.cross_context_world_robustness.v1"
MAX_CONTEXTS=3
MAX_CANDIDATES=4


class WorldRobustnessError(ValueError):
    """Cross-context world source, witness experiment or claim was rejected."""


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def _measured(proof,objective):
    facts=_summary(proof["world_state"])
    return {
        "campaign_digest":proof["digest"],
        "event_head_hash":proof["head_hash"],
        "metrics":facts,
        "objective_score":list(_score(facts,objective)),
        "direct_source_events":[{
            "lane":row["lane"],"world_tick":row["world_tick"],
            "event_id":row["source"].get("world_event_id"),
            "source_receipt":row["source"].get("source_receipt"),
            "firsthand_witnesses":row["source"].get("direct_witnesses",[]),
        } for row in proof["timeline"] if row["lane"]!="world"],
        "original_npc_memories":[
            {
                "id":npc["id"],"direct":list(npc["memories"]),
                "rumors":list(npc["heard"]),
            } for npc in proof["world_state"]["npcs"]
        ],
        "actual_world_state_digest":_hash(proof["world_state"]),
    }


def run_world_robustness(physical,genres,world_scenes,whatif,
                         world_settings=None,*,max_candidates=3):
    if (type(world_scenes) not in (list,tuple) or
        not 2<=len(world_scenes)<=MAX_CONTEXTS or
        type(max_candidates) is not int or
        not 1<=max_candidates<=MAX_CANDIDATES or
        type(whatif) is not dict or
        whatif.get("objective") not in OBJECTIVES):
        raise WorldRobustnessError(
            "two or three signed worlds and bounded original-source candidates required")
    try:
        settings=make_editor_document("quest_director",world_settings)["settings"]
        signed=[validate_advanced_scene(scene,settings)
                for scene in world_scenes]
        if (len({scene["digest"] for scene in signed})!=len(signed) or
            signed[0]["digest"]!=whatif.get("source_world_scene_digest")):
            raise WorldRobustnessError(
                "distinct authorized worlds must start with what-if baseline world")
        timeline=whatif["baseline"]["timeline"]
        verify_world_whatif(
            whatif,physical,genres,signed[0],timeline,settings)
        objective=whatif["objective"]
        baseline=[]
        for index,scene in enumerate(signed):
            proof=run_interleaved_world(
                physical,genres,scene,timeline,settings)
            verify_interleaved_world(
                proof,physical,genres,scene,timeline,settings)
            if index==0 and proof["digest"]!=whatif["baseline_campaign_digest"]:
                raise WorldRobustnessError("baseline original scene and source receipt diverged")
            baseline.append(_measured(proof,objective))
        accepted=[]
        rejected=[]
        for alternative in whatif["accepted_scenarios"][:max_candidates]:
            candidates=[]
            failed=None
            for context_index,scene in enumerate(signed):
                try:
                    proof=run_interleaved_world(
                        physical,genres,scene,alternative["timeline"],settings)
                    verify_interleaved_world(
                        proof,physical,genres,scene,alternative["timeline"],
                        settings)
                    if context_index==0 and proof["digest"]!=alternative["campaign_digest"]:
                        raise WorldRobustnessError(
                            "source candidate no longer reproduces original measured replay")
                    candidates.append(_measured(proof,objective))
                except (WorldRobustnessError,InterleavedWorldError,
                        ValueError,KeyError,IndexError,TypeError) as exc:
                    failed={
                        "scenario_id":alternative["scenario_id"],
                        "failed_context":context_index,
                        "cause":"real_original_game_or_npc_world_rejected",
                        "error_type":type(exc).__name__,
                    }
                    break
            if failed:
                rejected.append(failed)
                continue
            comparison=[]
            for index,measure in enumerate(candidates):
                score=tuple(measure["objective_score"])
                reference=tuple(baseline[index]["objective_score"])
                comparison.append({
                    "context_index":index,
                    "source_world_scene_digest":signed[index]["digest"],
                    "outperforms_baseline":score>reference,
                    "does_not_underperform_baseline":score>=reference,
                    "actual_measured_delta":{
                        key:measure["metrics"][key]-
                            baseline[index]["metrics"][key]
                        for key in METRICS
                    },
                })
            admitted={
                "scenario_id":alternative["scenario_id"],
                "timeline":alternative["timeline"],
                "source_swaps":alternative["swaps"],
                "context_outcomes":candidates,
                "context_comparisons":comparison,
                "strict_improvement_in_every_authored_context":all(
                    item["outperforms_baseline"] for item in comparison),
                "not_worse_in_any_authored_context":all(
                    item["does_not_underperform_baseline"]
                    for item in comparison),
                "worst_observed_objective_score":list(min(
                    tuple(item["objective_score"]) for item in candidates)),
                "all_world_sources_independently_replayed":True,
                "automatic_gameplay_committed":False,
                "native_hardware_certified":False,
            }
            accepted.append(admitted)
        # Select by the worst actually observed score. A result may be best
        # among tested alternatives without improving the authored baseline.
        accepted.sort(key=lambda item:(
            tuple(-n for n in item["worst_observed_objective_score"]),
            item["scenario_id"]))
        best=accepted[0] if accepted else None
        reference_worst=min(tuple(b["objective_score"]) for b in baseline)
        report={
            "schema":SCHEMA,"objective":objective,
            "world_scenes":[scene["digest"] for scene in signed],
            "source_whatif_digest":whatif["digest"],
            "baseline_worlds":baseline,
            "evaluated_candidates":len(whatif["accepted_scenarios"][:max_candidates]),
            "fully_replayed_candidates":accepted,
            "rejected_candidates":rejected,
            "selected_scenario_id":best["scenario_id"] if best else None,
            "selected_worst_observed_score":(
                best["worst_observed_objective_score"] if best else None),
            "worst_baseline_score":list(reference_worst),
            "selected_beats_worst_baseline":(
                tuple(best["worst_observed_objective_score"])>reference_worst
                if best else False),
            "selected_is_noninferior_in_all_contexts":(
                best["not_worse_in_any_authored_context"] if best else False),
            "selected_strictly_improves_every_context":(
                best["strict_improvement_in_every_authored_context"]
                if best else False),
            "source_project_files_mutated":False,
            "automatic_ai_weights_promoted":False,
            "population_generalization_claimed":False,
            "native_device_certified":False,
        }
        return {**report,"digest":_hash(report)}
    except WorldRobustnessError:
        raise
    except (ValueError,KeyError,IndexError,TypeError,WorldWhatIfError,
            InterleavedWorldError) as exc:
        raise WorldRobustnessError(
            "world contexts or counterfactual game sources failed independent review"
        ) from exc


def verify_world_robustness(proof,physical,genres,world_scenes,whatif,
                            settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise WorldRobustnessError("complete original multi-context proof required")
    try:
        reviewed=run_world_robustness(
            physical,genres,world_scenes,whatif,settings,
            max_candidates=proof["evaluated_candidates"] if
                 proof["evaluated_candidates"] else 1)
    except (TypeError,KeyError,ValueError) as exc:
        raise WorldRobustnessError("source scenario or candidate budget forged") from exc
    if reviewed!=proof:
        raise WorldRobustnessError(
            "false robustness, simulated witness or original NPC outcome claimed")
    return True


__all__=[
    "SCHEMA","MAX_CONTEXTS","MAX_CANDIDATES",
    "WorldRobustnessError","run_world_robustness","verify_world_robustness",
]
