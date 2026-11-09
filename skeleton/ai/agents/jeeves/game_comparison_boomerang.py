"""Bounded multi-game, boomerang-revisit native experimental curriculum.

Planning is deterministic, source-only and offline. Execution is opt-in,
delegated to the already sandboxed native comparative experiment owner.
Revisit "novelty" is a hash of *measured response patterns*, not model
training, causal identification or guaranteed new knowledge.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .game_comparison_schema import digest,validate_study
from .game_comparison_counterfactual import (
    _allowed_action,ComparativeExperimentError,
    verify_counterfactual_input_result,
)

SCHEMA="skeleton.game.comparison_boomerang_curriculum.v1"
RECEIPT_SCHEMA="skeleton.game.comparison_boomerang_progress.v1"
MAX_GAMES=10
MAX_TREATMENTS=8
MAX_REVISIT_ROUNDS=2
MAX_NATIVE_RUNS=480
MAX_TREATMENT_STEPS=64


def plan_comparison_boomerang(
    study: Mapping[str,Any], *,
    game_ids:list[str],
    treatments:int=3,
    revisit_rounds:int=2,
    repeats:int=2,
    candidate_actions:list[str]|None=None,
) -> dict[str,Any]:
    """Choose reproducible one-step interventions across each full cohort.

    No source ROM access, native emulation or training occurs in planning.
    """
    model=validate_study(dict(study))
    by_id={row["id"]:row for row in model["games"]}
    if (not isinstance(game_ids,list) or not 2<=len(game_ids)<=MAX_GAMES
        or len(set(game_ids))!=len(game_ids)
        or any(type(g) is not str or g not in by_id for g in game_ids)):
        raise ComparativeExperimentError("Boomerang selection must use 2–10 distinct source-study game IDs")
    if (type(treatments) is not int or not 1<=treatments<=MAX_TREATMENTS
        or type(revisit_rounds) is not int or not 0<=revisit_rounds<=MAX_REVISIT_ROUNDS
        or type(repeats) is not int or not 2<=repeats<=3):
        raise ComparativeExperimentError("Curriculum size, revisits or native repetitions exceed finite limits")
    selected=[by_id[game_id] for game_id in game_ids]
    if any(game["rights_evidence_digest"] is None for game in selected):
        raise ComparativeExperimentError("All native boomerang games require explicit local source-rights records")
    ports=[game["controller_devices"][0] for game in selected]
    if len(set(ports))!=1:
        raise ComparativeExperimentError(
            "A shared controlled-input curriculum requires the same first native controller device on all selected games"
        )
    default_actions=(
        ["idle","left","right","up","down","a","b","start","select"]
        if ports[0] in ("joypad","analog") else
        ["key_up","key_down","key_left","key_right","key_enter","key_space"]
    )
    actions=candidate_actions if candidate_actions is not None else default_actions
    if (not isinstance(actions,list) or not 1<=len(actions)<=16
        or any(type(action) is not str for action in actions)
        or len(set(actions))!=len(actions)
        or any(not _allowed_action(ports[0],action) for action in actions)):
        raise ComparativeExperimentError("Candidate action list must be a distinct approved native-device policy subset")
    if any(any(not _allowed_action(ports[0],a) for a in game["actions"]) for game in selected):
        raise ComparativeExperimentError("Input actions in a selected game do not match the native controller device")
    n=min(len(game["actions"]) for game in selected)
    if not 1<=n<=MAX_TREATMENT_STEPS:
        raise ComparativeExperimentError("Input tapes are outside the bounded experimental horizon")
    # Prefer early, quarter, middle, three-quarter, late, then fill gaps.
    landmarks=[
        1, max(1,(n+3)//4), max(1,(n+1)//2),
        max(1,(3*n+3)//4), n,
    ]
    steps=list(dict.fromkeys([*landmarks,*range(1,n+1)]))
    treatments_rows=[]
    for pos in steps:
        allowed=[
            action for action in actions
            if all(game["actions"][pos-1]!=action for game in selected)
        ]
        if not allowed:
            continue
        # Deterministically vary alternatives across stages instead of using
        # the same replacement at every early/middle/after checkpoint.
        offset=(pos+len(treatments_rows))%len(allowed)
        alternative=allowed[offset]
        if pos<=max(1,n//3):
            phase="earlier"
        elif pos<=max(1,(2*n)//3):
            phase="middle"
        else:
            phase="after"
        treatments_rows.append({
            "treatment_id":"step_"+str(pos)+"_"+alternative,
            "step":pos,"replacement_action":alternative,
            "phase":phase,
            "baseline_action_by_game":{
                game["id"]:game["actions"][pos-1] for game in selected
            },
        })
        if len(treatments_rows)>=treatments:
            break
    if len(treatments_rows)<treatments:
        raise ComparativeExperimentError(
            "Insufficient distinct valid intervention steps for the requested treatment count"
        )
    schedule=[]
    passes=1+revisit_rounds
    for round_index in range(passes):
        # Deterministic shuffle/boomerang: revisit early work interspersed
        # with later positions; alternate direction on each revisit pass.
        if round_index==0:
            ordering=list(range(len(treatments_rows)))
        else:
            ordered=sorted(
                range(len(treatments_rows)),
                key=lambda i:digest([
                    "boomerang",model["study_id"],round_index,
                    treatments_rows[i]["treatment_id"]
                ]),
            )
            ordering=ordered if round_index%2 else list(reversed(ordered))
        for slot,index in enumerate(ordering):
            target=treatments_rows[index]
            schedule.append({
                "slot":len(schedule),
                "round":round_index+1,
                "pass_kind":"initial" if round_index==0 else "boomerang_reinspection",
                "within_round_slot":slot,
                "treatment_id":target["treatment_id"],
                "step":target["step"],
                "replacement_action":target["replacement_action"],
                "phase":target["phase"],
                "game_ids":list(game_ids),
                "fresh_native_worker_runs":len(game_ids)*2*repeats,
            })
    estimated=len(schedule)*len(game_ids)*2*repeats
    if estimated>MAX_NATIVE_RUNS:
        raise ComparativeExperimentError(
            "Full boomerang queue would require too many isolated native runs"
        )
    report={
        "schema_version":SCHEMA,
        "source_study_id":model["study_id"],
        "study_manifest_sha256":digest(model),
        "selected_game_ids":list(game_ids),
        "first_controller_device":ports[0],
        "approved_candidate_actions":list(actions),
        "treatments":treatments_rows,
        "schedule":schedule,
        "rounds":passes,"repeats_per_arm":repeats,
        "games_per_cohort":len(game_ids),
        "estimated_fresh_native_worker_runs":estimated,
        "operator_must_acknowledge_run_budget":True,
        "actual_emulation_performed":False,
        "can_revisit_without_promoting_weights":True,
        "scientific_novelty_is_observational":True,
        "actual_ai_parameter_updates":0,
        "independent_gameplay_quality_gain_verified":False,
    }
    report["plan_sha256"]=digest(report)
    return report


def verify_boomerang_plan(plan:Mapping[str,Any],study:Mapping[str,Any])->dict[str,Any]:
    """Reject silently changed schedules/limits or foreign studies."""
    if (not isinstance(plan,dict) or plan.get("schema_version")!=SCHEMA
        or digest({key:value for key,value in plan.items() if key!="plan_sha256"})
            !=plan.get("plan_sha256")):
        raise ComparativeExperimentError("Boomerang queue SHA-256 root is missing or altered")
    verified=plan_comparison_boomerang(
        study,
        game_ids=plan.get("selected_game_ids"),
        treatments=len(plan.get("treatments",[])),
        revisit_rounds=plan.get("rounds",0)-1,
        repeats=plan.get("repeats_per_arm"),
        candidate_actions=plan.get("approved_candidate_actions"),
    )
    if verified!=plan:
        raise ComparativeExperimentError(
            "Boomerang plan differs from a fresh bounded source-study curriculum"
        )
    return verified


def experiment_signal_signature(result:Mapping[str,Any])->str|None:
    """Fingerprint repeatable *observed responses*, not experiment identity.

    A novel treatment ID, input action, source run root or fresh-worker
    repetition is NOT learning or newly observed audiovisual behavior.
    Confounded, nondeterministic and unchanged experiments have no
    reviewable response signature.
    """
    verify_counterfactual_input_result(result)
    rows=[]
    for row in result["games"]:
        analysis=row["measured_analysis"]
        if (
            analysis["scientific_evidence_status"]!="controlled_observable_signal_response_candidate"
            or not analysis["pre_intervention_controls_matched"]
            or not analysis["repeat_consistent_in_both_arms"]
            or not analysis["post_intervention_observable_response_candidate"]
        ):
            continue
        video=analysis["signal_comparison"]["video"]
        audio=analysis["signal_comparison"]["audio"]
        # Normalize first changes to treatment index so the same observed
        # response at a later chapter/step is not automatically 'new'.
        cursor=row["perturbation_step"]
        def lag(field:Mapping[str,Any])->int|None:
            first=field["first_repeatable_post_intervention_difference"]
            return (first-cursor) if first is not None else None
        rows.append({
            "game_id":row["game_id"],
            "video_first_repeatable_response_lag":lag(video),
            "audio_first_repeatable_response_lag":lag(audio),
            "actual_objective_deltas":analysis["measured_objective_changes"],
            "observed_multispectral_differences":(
                analysis.get("multispectral_abstract_comparison",{}).get(
                    "abstract_differences"
                ) if analysis.get("multispectral_abstract_comparison",{}).get(
                    "available",False
                ) else None
            ),
        })
    if not rows:
        return None
    return digest({
        "schema_version":"skeleton.game.boomerang_observed_response_fingerprint.v2",
        "observed_response_signatures":rows,
    })


def make_boomerang_progress(plan:Mapping[str,Any],results:list[Mapping[str,Any]])->dict[str,Any]:
    """Summarize only complete, locally verifiable A/B experiments."""
    if (not isinstance(plan,dict) or plan.get("schema_version")!=SCHEMA
        or plan.get("plan_sha256")!=digest({k:v for k,v in plan.items() if k!="plan_sha256"})):
        raise ComparativeExperimentError("Cannot summarize a modified curriculum plan")
    if (not isinstance(results,list) or len(results)>len(plan["schedule"])):
        raise ComparativeExperimentError("Progress exceeds the finite treatment schedule")
    observed=set()
    outcomes=[]
    rounds={}
    accepted_registry=None
    for index,result in enumerate(results):
        task=plan["schedule"][index]
        checked=verify_counterfactual_input_result(result)
        trial_registry=result["operator_core_registry_sha256"]
        if accepted_registry is None:
            accepted_registry=trial_registry
        elif accepted_registry!=trial_registry:
            raise ComparativeExperimentError(
                "Native curriculum replay sources differ in approved core registry authority"
            )
        if (result["source_study_id"]!=plan["source_study_id"]
            or result["source_manifest_sha256"]!=plan["study_manifest_sha256"]
            or result["input_step"]!=task["step"]
            or result["replacement_action"]!=task["replacement_action"]
            or result["game_count"]!=len(task["game_ids"])
            or [item["game_id"] for item in result["games"]]!=task["game_ids"]
            or result["fresh_native_runs_completed"]!=task["fresh_native_worker_runs"]):
            raise ComparativeExperimentError("Native experiment does not match its approved boomerang queue slot")
        signature=experiment_signal_signature(result)
        reviewable=signature is not None
        novel=reviewable and signature not in observed
        if reviewable:
            observed.add(signature)
        outcomes.append({
            "slot":index,"round":task["round"],
            "treatment_id":task["treatment_id"],
            "phase":task["phase"],
            "native_evidence_receipt_sha256":checked["verification_sha256"],
            "source_result_sha256":result["result_sha256"],
            "observation_signature_sha256":signature,
            "qualified_repeatable_response_observed":reviewable,
            "novel_observational_signal_pattern":novel,
            "measured_observation_not_model_learning":True,
        })
        round_summary=rounds.setdefault(task["round"],{
            "round":task["round"],"trials_completed":0,
            "previously_unseen_signatures":0,
        })
        round_summary["trials_completed"]+=1
        round_summary["previously_unseen_signatures"]+=int(novel)
        round_summary["repeatable_response_trials"]=round_summary.get(
            "repeatable_response_trials",0
        )+int(reviewable)
        round_summary["confounded_or_unchanged_trials"]=round_summary.get(
            "confounded_or_unchanged_trials",0
        )+int(not reviewable)
    total_done=sum(r["fresh_native_worker_runs"] for r in plan["schedule"][:len(results)])
    summary={
        "schema_version":RECEIPT_SCHEMA,
        "source_plan_sha256":plan["plan_sha256"],
        "source_study_id":plan["source_study_id"],
        "completed_treatments":len(results),
        "scheduled_treatments":len(plan["schedule"]),
        "remaining_treatments":len(plan["schedule"])-len(results),
        "fresh_native_worker_runs_completed":total_done,
        "approved_native_core_registry_sha256":accepted_registry,
        "novel_response_patterns_observed":len(observed),
        "unreviewable_or_no_repeatable_response_trials":sum(
            not row["qualified_repeatable_response_observed"] for row in outcomes
        ),
        "novelty_counts_only_repeatable_post_intervention_signals":True,
        "per_round_evidence":list(rounds.values()),
        "review_queue":outcomes,
        "status":"completed" if len(results)==len(plan["schedule"]) else "partial_with_pending_treatments",
        "boomerang_rediscovery_means_learned_weight":False,
        "dragon_scientific_review_pending":True,
        "production_model_weights_updated":0,
    }
    summary["progress_sha256"]=digest(summary)
    return summary
