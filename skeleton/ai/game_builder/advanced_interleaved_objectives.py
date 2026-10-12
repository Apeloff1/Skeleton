"""Pareto-aware objective matrix for independently replayed original games.

Every score is computed from actual canonical original-game NPC world states
produced by the independently verified counterfactual laboratory. Never
conflate source event order changes with real improvements in player-facing
gameplay. An explicit goal tradeoff is reported rather than silently ranked
as a verified win, and no AI training promotion or game mutation occurs.
"""
from __future__ import annotations

from hashlib import sha256
from copy import deepcopy
import json

from .advanced_interleaved_counterfactual import (
    run_counterfactual_lab,verify_counterfactual_lab,
    CounterfactualWorldError,
)

SCHEMA="skeleton.game_builder.causal_game_objective_matrix.v1"
OBJECTIVES=(
    "credible_eyewitness_reach",
    "earned_quest_completions",
    "original_site_restoration",
    "finite_material_resilience",
    "secondhand_rumor_reach",
)
MAX_GOALS=4


class ObjectiveMatrixError(ValueError):
    """Game objective, signed baseline or candidate score was rejected."""


def _sha(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def _goals(goals):
    if (type(goals) not in (tuple,list) or
        not 1<=len(goals)<=MAX_GOALS or
        any(type(goal) is not str or goal not in OBJECTIVES for goal in goals) or
        len(set(goals))!=len(goals)):
        raise ObjectiveMatrixError("one to four unique typed original-game design goals required")
    return list(goals)


def _metrics(snapshot):
    return {
        "credible_eyewitness_reach":sum(
            bool(memories) for _,memories in snapshot["direct_memory"]),
        "earned_quest_completions":snapshot["quests_completed"],
        "original_site_restoration":sum(snapshot["site_integrity"]),
        "finite_material_resilience":(
            sum(snapshot["site_stock"])+snapshot["player_resources"]["supplies"]),
        "secondhand_rumor_reach":sum(
            bool(memories) for _,memories in snapshot["rumor_memory"]),
    }


def _candidate_snapshot(original,candidate):
    data=deepcopy(original)
    for name,change in candidate["verified_deltas"].items():
        if name not in data or data[name]!=change["baseline"]:
            raise ObjectiveMatrixError("untrusted game causal difference contradicts baseline")
        data[name]=deepcopy(change["counterfactual"])
    return data


def _dominates(a,b):
    return all(x>=y for x,y in zip(a,b)) and any(
        x>y for x,y in zip(a,b))


def run_causal_objective_matrix(physical,genres,scene,timeline,settings=None,
                                *,goals=(
                                    "credible_eyewitness_reach",
                                    "earned_quest_completions"),
                                max_candidates=8):
    chosen=_goals(goals)
    try:
        laboratory=run_counterfactual_lab(
            physical,genres,scene,timeline,settings,max_candidates=max_candidates)
        verify_counterfactual_lab(
            laboratory,physical,genres,scene,timeline,settings)
        before=laboratory["baseline_snapshot"]
        base_metrics=_metrics(before)
        base_vector=[base_metrics[goal] for goal in chosen]
        scored=[]
        previous=_sha({"schema":SCHEMA,
                       "source_lab":laboratory["digest"],
                       "chosen_goals":chosen})
        for candidate in laboratory["candidates"]:
            if candidate["valid"]:
                metrics=_metrics(_candidate_snapshot(before,candidate))
                vector=[metrics[goal] for goal in chosen]
                deltas={goal:metrics[goal]-base_metrics[goal] for goal in chosen}
                better=any(value>0 for value in deltas.values())
                worse=any(value<0 for value in deltas.values())
                status=("strict_real_gameplay_improvement" if better and not worse
                        else "explicit_gameplay_tradeoff" if better and worse
                        else "verified_gameplay_regression" if worse
                        else "no_measured_gameplay_gain")
                item={
                    "candidate_index":candidate["candidate_index"],
                    "valid":True,
                    "candidate_digest":candidate["candidate_digest"],
                    "source_world_clock_digest":candidate["candidate_head_hash"],
                    "measured_metrics":metrics,
                    "goal_deltas":deltas,
                    "goal_vector":vector,
                    "classification":status,
                    "strictly_better_than_baseline":status=="strict_real_gameplay_improvement",
                    "pareto_frontier":False,
                }
            else:
                item={
                    "candidate_index":candidate["candidate_index"],
                    "valid":False,
                    "candidate_digest":None,
                    "source_world_clock_digest":None,
                    "measured_metrics":None,
                    "goal_deltas":None,
                    "goal_vector":None,
                    "classification":"original_source_timeline_invalid",
                    "strictly_better_than_baseline":False,
                    "pareto_frontier":False,
                }
            scored.append(item)
        for entry in scored:
            if not entry["valid"]:
                continue
            others=[base_vector]+[
                x["goal_vector"] for x in scored
                if x["valid"] and
                x["candidate_index"]!=entry["candidate_index"]]
            entry["pareto_frontier"]=not any(
                _dominates(other,entry["goal_vector"]) for other in others)
        for entry in scored:
            head=_sha({"previous":previous,"scored":entry})
            entry["previous_hash"]=previous
            entry["head_hash"]=head
            previous=head
        strict=[row for row in scored
                if row["strictly_better_than_baseline"]]
        # Stable deterministic priority order is lexicographic in the
        # USER'S reviewed goal sequence, not an invented weighted quality.
        strict.sort(key=lambda row:(
            *(-row["goal_deltas"][goal] for goal in chosen),
            row["candidate_index"]))
        suggested=strict[0]["candidate_index"] if strict else None
        result={
            "schema":SCHEMA,
            "original_source_lab_digest":laboratory["digest"],
            "baseline_campaign_digest":laboratory["baseline_campaign_digest"],
            "goals":chosen,
            "baseline_metrics":base_metrics,
            "baseline_goal_vector":base_vector,
            "candidate_results":scored,
            "candidate_count":len(scored),
            "verified_valid_candidates":sum(x["valid"] for x in scored),
            "verified_strict_improvements":len(strict),
            "observed_tradeoffs":sum(x["classification"]=="explicit_gameplay_tradeoff"
                                     for x in scored),
            "rejected_source_timelines":sum(not x["valid"] for x in scored),
            "suggested_candidate_index":suggested,
            "head_hash":previous,
            "original_project_files_changed":False,
            "automatic_game_event_application":False,
            "automatic_ai_weight_promotion":False,
            "native_multigenre_certification":False,
        }
    except ObjectiveMatrixError:
        raise
    except (CounterfactualWorldError,KeyError,TypeError,ValueError,IndexError) as exc:
        raise ObjectiveMatrixError(
            "original game world and causal design goals failed independent verification"
        ) from exc
    return {**result,"digest":_sha(result)}


def verify_causal_objective_matrix(proof,physical,genres,scene,timeline,
                                   settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise ObjectiveMatrixError("real game objective matrix proof required")
    try:
        source=run_causal_objective_matrix(
            physical,genres,scene,timeline,settings,
            goals=proof["goals"],max_candidates=proof["candidate_count"]
            if proof["candidate_count"] else 1)
    except (KeyError,TypeError) as exc:
        raise ObjectiveMatrixError("matrix omitted reviewable original game goals") from exc
    if source!=proof:
        raise ObjectiveMatrixError("forged game objective scores, Pareto proof or source history")
    return True


__all__=["SCHEMA","OBJECTIVES","MAX_GOALS","ObjectiveMatrixError",
         "run_causal_objective_matrix","verify_causal_objective_matrix"]
