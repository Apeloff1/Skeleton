"""Exact source-replayed factorial interaction and sensitivity audit.

A selected 2- or 3-factor combination is interrogated through EVERY
corner of its 2**k intervention lattice on two or three disjoint seeds.
Action factors use fixed command slots and neutral registered controls.
Setting factors use the actual original canonical editor. Every
corner receives an independent multispectral source replay. Pair/triple
Möbius effects are descriptive finite-world contrasts, not proof of
transfer, semantics, causal identification or full-game exhaustiveness.
"""
from __future__ import annotations

from hashlib import sha256
from itertools import combinations
import json
import math

from .game_studio_environment import make_studio_source, parse_studio_source
from skeleton.ai.game_builder.system_editors import editor_spec
from .game_studio_scenario_lab import _lane

SCHEMA="skeleton.game_builder.factorial_scrutiny.v1"
MAX_FACTORS=3
MAX_SEEDS=3
MAX_STEPS=8

class FactorialScrutinyError(ValueError):
    """Missing game intervention, invalid source, or divergent replay."""


def _digest(value):
    try:
        raw=json.dumps(value,sort_keys=True,separators=(",",":"),
                       allow_nan=False,ensure_ascii=True).encode()
    except (ValueError,TypeError,RecursionError) as exc:
        raise FactorialScrutinyError("factorial evidence requires finite canonical JSON") from exc
    return sha256(raw).hexdigest()


def _state_for_corner(base,axes,levels,active):
    settings=dict(base["settings"])
    for position in active:
        axis=axes[position]
        if axis["kind"]=="source_field":
            settings[axis["field"]]=axis["levels"][levels[position]]
    try:
        return make_studio_source(
            base["editor"],settings,scene=base["scene"],actions=base["actions"],
        )
    except (TypeError,ValueError) as exc:
        raise FactorialScrutinyError(
            "interaction subset violates original engine constraints"
        ) from exc


def _script_for_corner(source,axes,levels,changed_indices,active,steps,seed):
    actions=tuple(source["actions"])
    if not actions:
        raise FactorialScrutinyError("engine has no registered actions")
    neutral=next((v for v in ("inspect","observe","survey","wait","guard")
                  if v in actions),actions[0])
    # Slots are globally assigned to the changed action factors. This keeps
    # the command schedule aligned under any intervention/ablation.
    intervention_positions=[
        index for index in changed_indices if axes[index]["kind"]=="registered_action"
    ]
    if len(intervention_positions)>steps:
        raise FactorialScrutinyError(
            "more requested action interventions than actual game steps"
        )
    fillers=[a for a in actions if a not in {
        axes[i]["levels"][levels[i]] for i in intervention_positions
    } and a not in ("retire","finish")]
    if not fillers:
        fillers=[neutral]
    schedule=[fillers[(seed+step)%len(fillers)] for step in range(steps)]
    action_records=[]
    for slot,index in enumerate(intervention_positions):
        axis=axes[index]
        registered=axis["levels"][levels[index]]
        if index in active:
            if registered not in actions:
                raise FactorialScrutinyError("source action not registered")
            schedule[slot]=registered
        else:
            schedule[slot]=neutral
        action_records.append({
            "factor":axis["id"],"step":slot,"active":index in active,
            "command":schedule[slot],
        })
    return tuple(schedule),action_records


def scrutinize_interactions(
    source,axes,levels,*,seed=5,steps=3,seed_count=2,
    selected_indices=None,
):
    base=parse_studio_source(dict(source))
    if (type(axes) is not list or not 1<=len(axes)<=8
        or type(levels) not in (tuple,list) or len(axes)!=len(levels)
        or type(seed) is not int or not 0<=seed<=2**31-12000
        or type(steps) is not int or not 1<=steps<=MAX_STEPS
        or type(seed_count) is not int or not 2<=seed_count<=MAX_SEEDS):
        raise FactorialScrutinyError("bounded source-registered 2/3 factor scrutiny required")
    indexes=(
        [i for i,level in enumerate(levels) if level]
        if selected_indices is None else selected_indices
    )
    if (type(indexes) is not list or len(indexes)<2
        or len(indexes)>MAX_FACTORS or len(set(indexes))!=len(indexes)
        or any(type(i) is not int or i<0 or i>=len(axes)
               or levels[i]==0 for i in indexes)):
        raise FactorialScrutinyError("select two or three actual changed factors")
    if any(
        type(axis) is not dict or axis.get("kind") not in (
            "source_field","registered_action",
        ) or type(levels[i]) is not int
        or not 0<=levels[i]<len(axis.get("levels",[]))
        for i,axis in enumerate(axes)
    ):
        raise FactorialScrutinyError("unknown or forged factor choice")
    # The lattice is not permitted to invent arbitrary settings or action
    # controls. Recheck against the editor's actual typed source contract,
    # even when called outside the trusted scenario planner.
    catalog={f["key"]:f for f in editor_spec(base["editor"])["fields"]}
    for axis in axes:
        if type(axis) is not dict or type(axis.get("id")) is not str:
            raise FactorialScrutinyError("typed original-game factor identity required")
        if axis["kind"]=="source_field":
            key=axis.get("field")
            field=catalog.get(key)
            if (field is None or key in ("homebrew_only","license_gate")
                or axis["id"]!="setting:"+key
                or field["kind"] not in ("bool","int","enum")
                or axis["levels"][0]!=base["settings"][key]):
                raise FactorialScrutinyError("forged or rights-changing engine setting factor")
            if any(type(value)!=type(base["settings"][key])
                   for value in axis["levels"]):
                raise FactorialScrutinyError("factor values differ from original editor types")
        else:
            levels_list=axis.get("levels",[])
            if (len(levels_list)!=2 or levels_list[0] is not None
                or type(levels_list[1]) is not str
                or levels_list[1] not in base["actions"]
                or axis["id"]!="action:"+levels_list[1]):
                raise FactorialScrutinyError("factor action not registered in original source")
    indexes=sorted(indexes)
    axes_selected=[axes[i]["id"] for i in indexes]
    if len(set(axes_selected))!=len(axes_selected):
        raise FactorialScrutinyError("same control cannot be counted twice")
    cube=[]
    violations=[]
    responses=[]
    original_digest=_digest(base)
    reversed_execution_checks=0
    reversed_action_order_checks=0
    for offset in range(seed_count):
        # Independent stress seeds avoid both local optimizer seeds (+9000)
        # and heldout seeds (+14000). All corners within one cube get
        # the identical source seed and original command slot schedule.
        trial_seed=seed+1000*(offset+1)
        corners=[]
        scores={}
        for mask in range(1<<len(indexes)):
            active=[indexes[i] for i in range(len(indexes)) if mask&(1<<i)]
            try:
                edited=_state_for_corner(base,axes,levels,active)
                schedule,actuator=_script_for_corner(
                    base,axes,levels,indexes,active,steps,trial_seed,
                )
            except FactorialScrutinyError as exc:
                violations.append({
                    "seed":trial_seed,"mask":mask,
                    "reason":str(exc),"scope":"original_game_constraint",
                })
                break
            run=_lane(
                edited,"causal",trial_seed,steps,
                scripted_actions=schedule,
            )
            if run["audit_passed"] is not True or run["multispectral"]["passed_count"]!=10:
                raise FactorialScrutinyError("factor corner has no independent source audit")
            if len(run["transition_digests"])!=len(run["step_receipts"]):
                raise FactorialScrutinyError("corner transition custody broken")
            accepted={
                item["factor"]:any(
                    record["index"]==item["step"]+1 and
                    record["action"]==item["command"] and record["accepted"] is True
                    for record in run["step_receipts"]
                ) if item["active"] else None
                for item in actuator
            }
            record={
                "mask":mask,"source_digest":run["source_digest"],
                "source_seed":trial_seed,
                "actions":list(schedule),"interventions":actuator,
                "accepted_interventions":accepted,
                "executed_steps":run["steps"],
                "accepted_controls":run["accepted_actions"],
                "rejected_controls":run["rejected_actions"],
                "productive_state_changes":run["productive_state_changes"],
                "distinct_game_states":run["unique_gameplay_states"],
                "reward":run["total_reward"],
                "terminal_observation":run["last_observation"],
                "transition_digests":run["transition_digests"],
                "complete_step_receipts":run["step_receipts"],
                "trace_digest":run["digest"],
                "gameplay_trajectory_digest":run["gameplay_transition_states_digest"],
                "multispectral_audit_digest":run["multispectral"]["digest"],
                "checks_passed":run["multispectral"]["passed_count"],
                "physical_sensor_metrics_verified":False,
            }
            corners.append(record)
            scores[mask]=float(run["total_reward"])
        if len(corners)!=(1<<len(indexes)):
            continue
        # Independently re-execute the two extreme worlds in REVERSE
        # execution order after all intermediate factor combinations.
        # This catches hidden mutable-global/cross-sim contamination.
        for mask in ((1<<len(indexes))-1,0):
            active=[indexes[i] for i in range(len(indexes)) if mask&(1<<i)]
            rebuilt=_state_for_corner(base,axes,levels,active)
            replay_commands,_=_script_for_corner(
                base,axes,levels,indexes,active,steps,trial_seed,
            )
            replay=_lane(
                rebuilt,"causal",trial_seed,steps,
                scripted_actions=replay_commands,
            )
            if replay["digest"]!=corners[mask]["trace_digest"] or (
                replay["multispectral"]["digest"]!=
                corners[mask]["multispectral_audit_digest"]
            ):
                raise FactorialScrutinyError(
                    "game execution order contaminated independently repeated source"
                )
            reversed_execution_checks+=1
        if _digest(base)!=original_digest:
            raise FactorialScrutinyError("factor interventions changed original source")
        # A joint world with multiple timed controls is also probed using
        # the reverse sequence. Action composition need not commute in a
        # game; expose ordering-sensitive outcomes and rejection changes.
        original_actions=tuple(corners[-1]["actions"])
        reversed_actions=tuple(reversed(original_actions))
        order_receipt=None
        if len(original_actions)>1 and original_actions!=reversed_actions:
            joint_source=_state_for_corner(base,axes,levels,indexes)
            reversed_run=_lane(
                joint_source,"causal",trial_seed,steps,
                scripted_actions=reversed_actions,
            )
            if reversed_run["audit_passed"] is not True:
                raise FactorialScrutinyError("permuted multi-action episode lacks actual source audit")
            reversed_action_order_checks+=1
            order_receipt={
                "original_registered_action_sequence":list(original_actions),
                "reversed_registered_action_sequence":list(reversed_actions),
                "forward_trace_digest":corners[-1]["trace_digest"],
                "reordered_trace_digest":reversed_run["digest"],
                "reordered_multispectral_audit_digest":reversed_run["multispectral"]["digest"],
                "reordered_steps":reversed_run["steps"],
                "reordered_step_receipts":reversed_run["step_receipts"],
                "forward_reward":corners[-1]["reward"],
                "reordered_reward":reversed_run["total_reward"],
                "reordered_minus_forward_return":round(
                    reversed_run["total_reward"]-corners[-1]["reward"],7
                ),
                "rejected_action_change":(
                    reversed_run["rejected_actions"]-corners[-1]["rejected_controls"]
                ),
                "mechanical_order_sensitivity_observed":(
                    reversed_run["gameplay_transition_states_digest"]!=
                    corners[-1]["gameplay_trajectory_digest"]
                    or reversed_run["total_reward"]!=corners[-1]["reward"]
                    or reversed_run["accepted_actions"]!=corners[-1]["accepted_controls"]
                    or reversed_run["rejected_actions"]!=corners[-1]["rejected_controls"]
                ),
                "order_generalization_certified":False,
            }
        # Fully observed cube, not just a joint-world minus baseline score.
        main_effects=[]
        interaction_effects=[]
        for degree in range(1,len(indexes)+1):
            for positions in combinations(range(len(indexes)),degree):
                subset_mask=sum(1<<p for p in positions)
                members=tuple(mask for mask in range(1<<len(indexes))
                              if mask&~subset_mask==0)
                coefficient=round(sum(
                    ((-1)**(degree-bin(mask).count("1")))*scores[mask]
                    for mask in members
                ),7)
                result={"order":degree,
                        "factors":[axes_selected[p] for p in positions],
                        "contrast":coefficient,
                        "source_cells":[{"mask":mask,"reward":scores[mask]}
                                        for mask in members]}
                if degree==1:main_effects.append(result)
                else:interaction_effects.append(result)
        cube.append({
            "seed":trial_seed,
            "corners":corners,
            "main_effects":main_effects,
            "interaction_effects":interaction_effects,
            "reordered_actions_scrutiny":order_receipt,
            "paired_joint_return_delta":round(
                scores[(1<<len(indexes))-1]-scores[0],7,
            ),
            "joint_all_action_interventions_accepted":all(
                value is not False
                for value in corners[-1]["accepted_interventions"].values()
            ),
        })
        responses.append(cube[-1]["paired_joint_return_delta"])
    # No unique signal can be inferred if any planned seed cube failed;
    # failures are visible as incompleteness, not reallocated to other
    # seeds that would contaminate matched-pair sensitivity.
    complete=len(cube)==seed_count and not violations
    effect_keys={}
    for experiment in cube:
        for row in experiment["main_effects"]+experiment["interaction_effects"]:
            key=(row["order"],tuple(row["factors"]))
            effect_keys.setdefault(key,[]).append(row["contrast"])
    sensitivity=[]
    for (order,names),values in sorted(effect_keys.items()):
        sensitivity.append({
            "order":order,"factors":list(names),
            "per_seed_contrasts":values,
            "mean":round(math.fsum(values)/len(values),7),
            "min":min(values),"max":max(values),
            "sign_reversal_between_seeds":(
                any(x>0 for x in values) and any(x<0 for x in values)
            ),
            "range":round(max(values)-min(values),7),
            "population_standard_deviation":round(
                math.sqrt(math.fsum(
                    (v-math.fsum(values)/len(values))**2 for v in values
                )/len(values)),7,
            ),
            "negative_seed_count":sum(x<0 for x in values),
            "positive_seed_count":sum(x>0 for x in values),
            "zero_seed_count":sum(x==0 for x in values),
            "sign_consistency_across_tested_seeds":(
                all(x>0 for x in values) or all(x<0 for x in values)
                or all(x==0 for x in values)
            ),
            "statistical_significance_established":False,
        })
    # Risk is grounded in the sampled source evidence and is only a
    # scheduler priority for further scrutiny. It is not a substitute
    # for actual heldout policy metrics, causal identification or safety.
    order_regressions=sum(
        row["reordered_actions_scrutiny"] is not None and
        row["reordered_actions_scrutiny"]["reordered_minus_forward_return"]<0
        for row in cube
    )
    action_rejections=sum(
        not row["joint_all_action_interventions_accepted"]
        for row in cube
    )
    sign_flips=sum(row["sign_reversal_between_seeds"] for row in sensitivity)
    negative_seeds=sum(value<0 for value in responses)
    reasons=[]
    if not complete:reasons.append("incomplete_or_illegal_intervention_cube")
    if sign_flips:reasons.append("factor_interaction_reverses_sign_between_seeds")
    if negative_seeds:reasons.append("joint_reward_regression_on_matched_seed")
    if order_regressions:reasons.append("reversed_action_order_worse_than_forward")
    if action_rejections:reasons.append("selected_factor_action_rejected")
    if any(level and i not in indexes for i,level in enumerate(levels)):
        reasons.append("some_changed_factors_not_examined")
    priority=min(100,
        12*len(reasons)
        +min(20,5*negative_seeds)
        +min(15,5*sign_flips)
        +min(15,5*order_regressions)
    )
    report={
        "schema_version":SCHEMA,
        "base_source_digest":_digest(base),
        "base_seed":seed,"steps_per_cell":steps,
        "axes":axes_selected,
        "source_axis_positions":indexes,
        "other_active_axes_not_examined":[
            axes[i]["id"] for i,level in enumerate(levels)
            if level and i not in indexes
        ],
        "seed_count_requested":seed_count,
        "complete_seed_cubes":len(cube),
        "exact_cells_per_seed":1<<len(indexes),
        "source_replayed_corner_count":sum(len(row["corners"]) for row in cube),
        "audited_checks_count":sum(
            entry["checks_passed"] for row in cube for entry in row["corners"]
        )+10*(reversed_execution_checks+reversed_action_order_checks),
        "reversed_order_independent_replays":reversed_execution_checks,
        "reversed_order_scrutiny_checks":10*reversed_execution_checks,
        "reordered_action_scrutiny_runs":reversed_action_order_checks,
        "reordered_action_scrutiny_checks":10*reversed_action_order_checks,
        "total_audited_source_episode_checks":10*(
            sum(len(row["corners"]) for row in cube)
            +reversed_execution_checks+reversed_action_order_checks
        ),
        "seed_cubes":cube,
        "constraint_violations":violations,
        "sensitivity":sensitivity,
        "matched_seed_joint_return_differences":responses,
        "adversarial_reexamination_priority":{
            "score":priority,
            "reasons":reasons,
            "recommended":bool(reasons),
            "proposed_additional_source_seeds":[seed+4000,seed+5000]
                 if reasons else [],
            "additional_gameplay_sims_executed":0,
            "no_background_automation_claimed":True,
            "targeted_followup_requires_new_authorized_run":True,
        },
        "mean_matched_seed_delta":(
            round(math.fsum(responses)/len(responses),7)
            if responses else None
        ),
        "worst_seed_joint_return_delta":min(responses) if responses else None,
        "source_factorial_design_complete":complete,
        "whole_joint_variant_examined":complete and not any(
            level and i not in indexes for i,level in enumerate(levels)
        ),
        "observed_joint_gain_proven":(
            complete and all(row["joint_all_action_interventions_accepted"]
                             for row in cube)
            and all(v>0 for v in responses)
        ),
        "robust_joint_gain_under_tested_orders":(
            complete and all(row["joint_all_action_interventions_accepted"]
                             for row in cube)
            and all(v>0 for v in responses)
            and order_regressions==0
        ),
        "source_unmodified_by_interventions":_digest(base)==original_digest,
        "source_simulation_order_invariance_tested":reversed_execution_checks>0,
        "permuted_action_order_tested":reversed_action_order_checks>0,
        "observed_action_order_regression_count":sum(
            1 for row in cube
            if row["reordered_actions_scrutiny"] is not None
            and row["reordered_actions_scrutiny"]["reordered_minus_forward_return"]<0
        ),
        "observed_action_order_mechanics_difference_count":sum(
            1 for row in cube
            if row["reordered_actions_scrutiny"] is not None
            and row["reordered_actions_scrutiny"]["mechanical_order_sensitivity_observed"]
        ),
        "sample_scope_only":True,
        "causal_identification_generalized":False,
        "training_weight_updates":0,
        "native_multispectral_camera_claimed":False,
    }
    return {**report,"digest":_digest(report)}


def verify_factorial_receipt(source,axes,levels,receipt,*,steps):
    """Full independent game replay for every stored factor-lattice corner."""
    if (type(receipt) is not dict
        or receipt.get("steps_per_cell")!=steps
        or type(receipt.get("base_seed")) is not int):
        raise FactorialScrutinyError("verified factorial evidence lacks source replay bounds")
    expected=scrutinize_interactions(
        source,axes,levels,
        seed=receipt["base_seed"],
        steps=steps,
        seed_count=receipt["seed_count_requested"],
        selected_indices=receipt["source_axis_positions"],
    )
    if receipt!=expected:
        raise FactorialScrutinyError("persisted factorial scrutiny diverged from replay")
    return True
