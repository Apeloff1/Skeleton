"""Real, bounded controlled-input experiments for comparative emulator learning.

For 2–10 independently selected, rights-acknowledged native games,
compare matched baseline and one-step-perturbed input tapes across fresh
approved libretro workers. Repeat each arm, inspect within-arm determinism,
and extract transparent audiovisual/response differences—not machine-learning
weight improvements, strategic mastery, or proof of a game mechanic.
"""
from __future__ import annotations

import math
import shutil
import tempfile
from collections.abc import Mapping
from typing import Any

from .game_comparison_schema import ComparativeStudyError, digest, validate_study
from .game_comparison_media import prepare_comparison_media
from .game_emulator_catalog import GameEmulatorRegistry
from .game_emulator_host import _ACTIONS, _KEY_ACTIONS, create_emulator_environment

SCHEMA="skeleton.game.comparison_counterfactual_input_v1"
MAX_GAMES=10
MAX_REPEATS=3
MAX_STEPS=64


class ComparativeExperimentError(ValueError):
    """The native controlled experiment is unapproved or invalid."""


def _allowed_action(device: str, action: str) -> bool:
    return (device in ("joypad","analog") and action in _ACTIONS
            or device=="keyboard" and action in _KEY_ACTIONS)


def _validate_design(
    study: Mapping[str,Any], *,
    game_ids: list[str], step: int, replacement_action: str,
    repeats: int,
) -> tuple[dict[str,Any],list[dict[str,Any]]]:
    model=validate_study(dict(study))
    games={game["id"]:game for game in model["games"]}
    if (not isinstance(game_ids,list) or not 2<=len(game_ids)<=MAX_GAMES
        or any(type(value) is not str for value in game_ids)
        or len(set(game_ids))!=len(game_ids)
        or any(value not in games for value in game_ids)):
        raise ComparativeExperimentError("Select 2–10 unique games in the validated study")
    if type(step) is not int or step<1 or step>MAX_STEPS:
        raise ComparativeExperimentError("Single perturbation step must be within 1–64")
    if type(replacement_action) is not str or replacement_action not in (*_ACTIONS,*_KEY_ACTIONS):
        raise ComparativeExperimentError("Replacement is not a declared libretro policy action")
    if type(repeats) is not int or not 2<=repeats<=MAX_REPEATS:
        raise ComparativeExperimentError("Use two or three fresh native repetitions of each arm")
    selected=[games[game_id] for game_id in game_ids]
    for game in selected:
        actions=game["actions"]
        device=game["controller_devices"][0]
        if step>len(actions):
            raise ComparativeExperimentError("One source game's tape is shorter than perturbation step")
        if not _allowed_action(device,replacement_action) or not all(
            _allowed_action(device,x) for x in actions
        ):
            raise ComparativeExperimentError("Experiment action does not match the source game's first controller device")
        if actions[step-1]==replacement_action:
            raise ComparativeExperimentError("Replacement is identical to baseline action for a selected game")
        if game["rights_evidence_digest"] is None:
            raise ComparativeExperimentError("Native scientific game observations require an explicit source-rights receipt")
    return model,selected


def _arm(
    game: Mapping[str,Any], *,
    actions: list[str], registry: GameEmulatorRegistry,
    contents: dict[str,Any], content_sha256: str,
    repeated_index: int, arm: str,
) -> dict[str,Any]:
    """Actual fresh libretro worker run; never use a synthetic observation."""
    evidence=[]
    chain=digest(["comparative-controlled-native-run",
                  registry.registry_digest,content_sha256,
                  game["id"],arm,repeated_index,game["seed"]])
    from .game_comparison_multispectral import native_step_multispectral_receipt

    with create_emulator_environment(
        game["target_id"],core_id=game["core_id"],
        expected_registry_digest=registry.registry_digest,
        **contents,controller_devices=game["controller_devices"],
        max_steps=len(actions),frames_per_step=game["frames_per_step"],
        timeout_seconds=5.0,
    ) as env:
        env.reset(game["seed"])
        for index, action in enumerate(actions,1):
            prior_frame=dict(env._frame) if isinstance(env._frame,dict) else None
            prior_pixels=env._pixels
            result=env.step(action)
            frame=env._frame
            if not isinstance(frame,dict):
                raise ComparativeExperimentError("Native worker did not return an actual frame")
            observations={
                metric:float(result.observation[metric])
                for metric in ("screen_mean","visual_change","audio_rms","step_fraction")
            }
            if any(not math.isfinite(value) for value in observations.values()):
                raise ComparativeExperimentError("Nonfinite measured native objective evidence")
            multispectral=native_step_multispectral_receipt(
                prior_frame,prior_pixels,frame,env._pixels,env._audio,
            )
            receipt={
                "step":index,"action":action,
                "source":"actual_isolated_libretro",
                "source_game_sha256":content_sha256,
                "core_sha256":env.core.library_sha256,
                "native_frame_sha256":frame["pixel_sha256"],
                "native_pcm_sha256":frame["audio_sha256"],
                "native_transition_sha256":result.transition_digest,
                "observations":observations,
                "native_multispectral":multispectral,
                "native_gameplay_goal_verified":False,
            }
            chain=digest([chain,receipt])
            receipt["receipt_chain_sha256"]=chain
            evidence.append(receipt)
            if env.done and index!=len(actions):
                raise ComparativeExperimentError(
                    "Actual native episode ended before the planned counterfactual action sequence"
                )
    return {
        "arm":arm,"repeat":repeated_index,
        "actions_sha256":digest(actions),
        "seed":game["seed"],"native_steps_executed":len(evidence),
        "receipts":evidence,"last_evidence_sha256":chain,
        "real_native_run":True,"fresh_worker_requested":True,
        "external_execution_attestation":False,
    }


def _analyze_counterfactual(
    baseline: list[dict[str,Any]], variant: list[dict[str,Any]], *,
    perturbation_step:int,
) -> dict[str,Any]:
    """Compare *paired native repeats* and reject pre-intervention divergence.

    This measures frame/audio differences. Even a clean difference is not
    proof of a game mechanic, generalized ability or production-model gain.
    """
    if (not baseline or len(baseline)!=len(variant)
        or type(perturbation_step) is not int):
        raise ComparativeExperimentError("Matched controlled experiment arms are required")
    a_runs=[run["receipts"] for run in baseline]
    b_runs=[run["receipts"] for run in variant]
    n=len(a_runs[0])
    if (not 1<=perturbation_step<=n
        or any(len(row)!=n for row in a_runs+b_runs)):
        raise ComparativeExperimentError("All actual native A/B tapes require identical step counts")
    outcomes={}
    for source_field,label in (
        ("native_frame_sha256","video"),("native_pcm_sha256","audio")
    ):
        def stable(runs:list[list[dict[str,Any]]])->bool:
            return all(
                all(run[i][source_field]==runs[0][i][source_field]
                    for i in range(n))
                for run in runs[1:]
            )
        bstable=stable(a_runs)
        vstable=stable(b_runs)
        per_step_agreement=[]
        for index in range(n):
            comparisons=[
                a[index][source_field]!=b[index][source_field]
                for a,b in zip(a_runs,b_runs,strict=True)
            ]
            per_step_agreement.append({
                "step":index+1,
                "different_paired_repeats":sum(comparisons),
                "total_paired_repeats":len(comparisons),
                "consistently_different":all(comparisons),
                "consistently_equal":not any(comparisons),
            })
        prefix_consistent=all(
            entry["consistently_equal"]
            for entry in per_step_agreement[:perturbation_step-1]
        )
        changed=[
            item["step"] for item in per_step_agreement
            if item["different_paired_repeats"]>0
        ]
        repeat_stable=bstable and vstable
        post_consistently_changed=[
            item["step"] for item in per_step_agreement[perturbation_step-1:]
            if item["consistently_different"]
        ]
        outcomes[label]={
            "first_observed_difference_step":changed[0] if changed else None,
            "different_frame_or_audio_steps":changed,
            "difference_at_perturbed_input_step":perturbation_step in changed,
            "same_at_end":(n not in changed),
            "baseline_same_across_fresh_repeats":bstable,
            "perturbed_same_across_fresh_repeats":vstable,
            "pre_intervention_equal_in_every_paired_run":prefix_consistent,
            "first_repeatable_post_intervention_difference":(
                post_consistently_changed[0] if post_consistently_changed else None
            ),
            "paired_repeat_differences_by_step":per_step_agreement,
            "unconfounded_signal_response_observed":(
                prefix_consistent and repeat_stable and bool(post_consistently_changed)
            ),
        }
    measured_delta={}
    per_pair_deltas={}
    for key in ("screen_mean","visual_change","audio_rms"):
        values=[
            float(b[perturbation_step-1]["observations"][key])-
            float(a[perturbation_step-1]["observations"][key])
            for a,b in zip(a_runs,b_runs,strict=True)
        ]
        if any(not math.isfinite(value) for value in values):
            raise ComparativeExperimentError("Invalid numeric native comparison result")
        measured_delta[key+"_at_changed_step"]=round(sum(values)/len(values),8)
        per_pair_deltas[key+"_paired_repeats"]=[
            round(value,8) for value in values
        ]
    matched_prefix=all(
        signal["pre_intervention_equal_in_every_paired_run"]
        for signal in outcomes.values()
    )
    stable_arms=all(
        signal["baseline_same_across_fresh_repeats"]
        and signal["perturbed_same_across_fresh_repeats"]
        for signal in outcomes.values()
    )
    post_response=any(
        signal["unconfounded_signal_response_observed"]
        for signal in outcomes.values()
    )
    if not matched_prefix:
        status="invalid_pre_intervention_divergence"
    elif not stable_arms:
        status="insufficient_native_repeatability"
    elif post_response:
        status="controlled_observable_signal_response_candidate"
    else:
        status="no_repeatable_audiovisual_difference"
    # Abstract physics/audio texture descriptors are logged, not raw source
    # frames, sound buffers, melodies or copied expressive material.
    from .game_comparison_multispectral import summarize_multispectral_change

    a_multi=a_runs[0][perturbation_step-1].get("native_multispectral")
    b_multi=b_runs[0][perturbation_step-1].get("native_multispectral")
    if (isinstance(a_multi,dict) and isinstance(b_multi,dict)
        and a_multi.get("spatial") is not None
        and b_multi.get("spatial") is not None):
        multi_comparison={
            "available":True,
            "abstract_differences":summarize_multispectral_change(a_multi,b_multi),
            "source_frame_sha256_pair":[
                a_multi["source_frame_sha256"],b_multi["source_frame_sha256"]
            ],
            "source_pcm_sha256_pair":[
                a_multi["source_pcm_sha256"],b_multi["source_pcm_sha256"]
            ],
            "no_game_semantics_inferred":True,
        }
    else:
        multi_comparison={
            "available":False,
            "reason":"Native spatial motion unavailable or geometry changed",
            "no_game_semantics_inferred":True,
        }
    return {
        "measured_objective_changes":measured_delta,
        "multispectral_abstract_comparison":multi_comparison,
        "paired_numeric_observation_deltas":per_pair_deltas,
        "signal_comparison":outcomes,
        "repeat_consistent_in_both_arms":stable_arms,
        "pre_intervention_controls_matched":matched_prefix,
        "scientific_evidence_status":status,
        "post_intervention_observable_response_candidate":(
            matched_prefix and stable_arms and post_response
        ),
        "design_controls":{
            "same_approved_binary":True,
            "same_original_media_sha256":True,
            "same_episode_seed_label":True,
            "same_frames_per_step":True,
            "only_one_user_input_token_modified":True,
            "repetitions_per_arm":len(baseline),
            "pre_intervention_observations_identical":matched_prefix,
            "uncontrolled_game_randomness_excluded":False,
            "causal_game_mechanic_proven":False,
        },
        "trainable_high_level_model_parameters_identified":False,
        "production_model_weights_updated":0,
        "heldout_learning_gain_verified":False,
    }


def run_counterfactual_input_study(
    study: Mapping[str,Any], *,
    game_ids:list[str],step:int,replacement_action:str,
    repeats:int=2,registry:GameEmulatorRegistry|None=None,
) -> dict[str,Any]:
    model,selected=_validate_design(
        study,game_ids=game_ids,step=step,replacement_action=replacement_action,
        repeats=repeats,
    )
    current=registry or GameEmulatorRegistry.from_environment()
    from .game_comparison_studio import _storage_waves

    # Each run creates two temporary content copies; native arms run
    # sequentially, but a single game must fit the same conservative budget.
    _storage_waves(
        selected,
        requested_slots=1,
        free_temp_bytes=shutil.disk_usage(tempfile.gettempdir()).free,
    )
    for game in selected:
        approved=current.resolve_core(game["core_id"])
        if game["target_id"] not in approved.target_ids:
            raise ComparativeExperimentError("Installed core lacks the selected game's exact target")
    games=[]
    for game in selected:
        original=list(game["actions"])
        alternate=list(original)
        alternate[step-1]=replacement_action
        # Materialize only one game's source at a time; no 30-ROM copies.
        content,source_sha=prepare_comparison_media(game)
        baseline=[]
        variant=[]
        # Interleave actual execution to reduce machine-time ordering bias.
        for iteration in range(1,repeats+1):
            if iteration%2:
                baseline.append(_arm(
                    game,actions=original,registry=current,contents=content,
                    content_sha256=source_sha,repeated_index=iteration,arm="baseline",
                ))
                variant.append(_arm(
                    game,actions=alternate,registry=current,contents=content,
                    content_sha256=source_sha,repeated_index=iteration,arm="perturbed",
                ))
            else:
                variant.append(_arm(
                    game,actions=alternate,registry=current,contents=content,
                    content_sha256=source_sha,repeated_index=iteration,arm="perturbed",
                ))
                baseline.append(_arm(
                    game,actions=original,registry=current,contents=content,
                    content_sha256=source_sha,repeated_index=iteration,arm="baseline",
                ))
        analysis=_analyze_counterfactual(
            baseline,variant,perturbation_step=step,
        )
        games.append({
            "game_id":game["id"],"core_id":game["core_id"],
            "target_id":game["target_id"],"source_sha256":source_sha,
            "perturbation_step":step,
            "baseline_action":original[step-1],
            "alternative_action":replacement_action,
            "original_actions_sha256":digest(original),
            "perturbed_actions_sha256":digest(alternate),
            "baseline_fresh_native_runs":baseline,
            "perturbed_fresh_native_runs":variant,
            "measured_analysis":analysis,
            "source_rights_independently_verified":False,
        })
    result={
        "schema_version":SCHEMA,
        "source_study_id":model["study_id"],
        "source_manifest_sha256":digest(model),
        "operator_core_registry_sha256":current.registry_digest,
        "game_count":len(games),
        "fresh_native_runs_attempted":len(games)*repeats*2,
        "fresh_native_runs_completed":sum(
            len(row["baseline_fresh_native_runs"])+len(row["perturbed_fresh_native_runs"])
            for row in games
        ),
        "input_step":step,"replacement_action":replacement_action,
        "games":games,
        "actual_native_content_required":True,
        "source_game_logic_reverse_engineered":False,
        "holdout_validation_completed":False,
        "dragon_review_authority_granted":False,
        "production_model_weights_promoted":False,
    }
    result["result_sha256"]=digest(result)
    return result


def verify_counterfactual_input_result(report: Mapping[str,Any]) -> dict[str,Any]:
    """Recompute every native A/B input and stage receipt before Dragon review.

    Tamper evidence is local SHA chaining, NOT third-party execution
    attestation. No behavior or model-training quality can be inferred.
    """
    if (not isinstance(report,dict) or report.get("schema_version")!=SCHEMA
        or digest({k:v for k,v in report.items() if k!="result_sha256"})
            !=report.get("result_sha256")):
        raise ComparativeExperimentError("Controlled native experiment root was changed")
    games=report.get("games")
    repeats=report.get("fresh_native_runs_completed")
    if (not isinstance(games,list) or not 2<=len(games)<=MAX_GAMES
        or report.get("game_count")!=len(games)
        or type(repeats) is not int
        or repeats!=report.get("fresh_native_runs_attempted")):
        raise ComparativeExperimentError("Controlled native game cohort or run count differs")
    observed_games=set()
    verified_steps=0
    verified_runs=0
    for game in games:
        if not isinstance(game,dict):
            raise ComparativeExperimentError("Native trial game record is missing")
        gid=game.get("game_id")
        if type(gid) is not str or gid in observed_games:
            raise ComparativeExperimentError("Native trial game identity is not unique")
        observed_games.add(gid)
        source=game.get("source_sha256")
        changed_step=game.get("perturbation_step")
        original=game.get("baseline_action")
        replacement=game.get("alternative_action")
        if (type(source) is not str or len(source)!=64
            or type(changed_step) is not int or not 1<=changed_step<=MAX_STEPS
            or changed_step!=report.get("input_step")
            or replacement!=report.get("replacement_action")
            or type(original) is not str or type(replacement) is not str
            or original==replacement):
            raise ComparativeExperimentError("One controlled input alteration differs from study design")
        arms={
            "baseline":game.get("baseline_fresh_native_runs"),
            "perturbed":game.get("perturbed_fresh_native_runs"),
        }
        if (not all(isinstance(v,list) and 2<=len(v)<=MAX_REPEATS
                    for v in arms.values())
            or len(arms["baseline"])!=len(arms["perturbed"])):
            raise ComparativeExperimentError("A/B native execution repetitions are incomplete")
        tapes={}
        known_core=None
        for arm,runs in arms.items():
            identifiers=set()
            for run in runs:
                if (not isinstance(run,dict) or run.get("arm")!=arm
                    or run.get("real_native_run") is not True
                    or run.get("fresh_worker_requested") is not True
                    or type(run.get("repeat")) is not int):
                    raise ComparativeExperimentError("Native A/B run identity or execution flag is absent")
                index=run["repeat"]
                if index in identifiers or not 1<=index<=len(runs):
                    raise ComparativeExperimentError("Native A/B repeat number was duplicated or omitted")
                identifiers.add(index)
                evidence=run.get("receipts")
                if (not isinstance(evidence,list) or not 3<=len(evidence)<=MAX_STEPS
                    or run.get("native_steps_executed")!=len(evidence)):
                    raise ComparativeExperimentError("Native experiment lacks a bounded complete tape")
                chain=digest([
                    "comparative-controlled-native-run",
                    report["operator_core_registry_sha256"],
                    source,gid,arm,index,run["seed"],
                ])
                actions=[]
                for step,receipt in enumerate(evidence,1):
                    if not isinstance(receipt,dict):
                        raise ComparativeExperimentError("Measured frame/PCM receipt is not an object")
                    body={k:v for k,v in receipt.items() if k!="receipt_chain_sha256"}
                    chain=digest([chain,body])
                    if (receipt.get("receipt_chain_sha256")!=chain
                        or receipt.get("step")!=step
                        or receipt.get("source")!="actual_isolated_libretro"
                        or receipt.get("source_game_sha256")!=source):
                        raise ComparativeExperimentError("Native controlled experiment evidence chain was changed")
                    core=receipt.get("core_sha256")
                    if type(core) is not str or len(core)!=64:
                        raise ComparativeExperimentError("Actual native core binary hash is absent")
                    if known_core is not None and core!=known_core:
                        raise ComparativeExperimentError("Different native core binary used between A/B experiment arms")
                    known_core=core
                    action=receipt.get("action")
                    if not isinstance(action,str) or action not in (*_ACTIONS,*_KEY_ACTIONS):
                        raise ComparativeExperimentError("Actual native input action is not recorded")
                    for key in ("native_frame_sha256","native_pcm_sha256","native_transition_sha256"):
                        value=receipt.get(key)
                        if type(value) is not str or len(value)!=64:
                            raise ComparativeExperimentError("Native audiovisual/transition source identity is missing")
                    measured=receipt.get("observations")
                    if (not isinstance(measured,dict)
                        or any(type(measured.get(name)) not in (int,float)
                               or not math.isfinite(measured[name])
                               for name in ("screen_mean","visual_change","audio_rms","step_fraction"))):
                        raise ComparativeExperimentError("Actual numeric native measurements were changed")
                    actions.append(action)
                if (run.get("last_evidence_sha256")!=chain
                    or run.get("actions_sha256")!=digest(actions)):
                    raise ComparativeExperimentError("Run final proof differs from its controller tape")
                if arm not in tapes:
                    tapes[arm]=actions
                elif tapes[arm]!=actions:
                    raise ComparativeExperimentError("A/B arm repetitions did not use identical declared controller tapes")
                verified_runs+=1
                verified_steps+=len(evidence)
        # A forged/accidentally stale analysis can otherwise describe signal
        # differences that are not present in its very own run receipts.
        recomputed=_analyze_counterfactual(
            arms["baseline"], arms["perturbed"],
            perturbation_step=changed_step,
        )
        if digest(recomputed)!=digest(game.get("measured_analysis")):
            raise ComparativeExperimentError(
                "Controlled signal conclusions differ from native frame/audio receipts"
            )
        base=tapes["baseline"]
        altered=tapes["perturbed"]
        if (len(base)!=len(altered) or changed_step>len(base)
            or base[changed_step-1]!=original
            or altered[changed_step-1]!=replacement
            or sum(x!=y for x,y in zip(base,altered,strict=True))!=1
            or digest(base)!=game.get("original_actions_sha256")
            or digest(altered)!=game.get("perturbed_actions_sha256")):
            raise ComparativeExperimentError("Controlled source-input tapes differ in more than one action")
    if verified_runs!=repeats:
        raise ComparativeExperimentError("Verified native fresh-worker repetition count differs")
    result={
        "schema_version":"skeleton.game.counterfactual_evidence_verification.v1",
        "study_id":report["source_study_id"],
        "source_result_sha256":report["result_sha256"],
        "game_count":len(games),
        "fresh_native_runs_hash_checked":verified_runs,
        "native_action_observations_hash_checked":verified_steps,
        "exact_one_action_changed_per_game":True,
        "same_native_core_sha_per_game_across_arms":True,
        "independent_external_execution_attestation":False,
        "production_ai_parameters_or_weights_promoted":False,
    }
    result["verification_sha256"]=digest(result)
    return result
