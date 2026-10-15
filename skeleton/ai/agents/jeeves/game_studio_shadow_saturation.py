"""Per-simulation shadow clones and evidence-saturation learning laboratory.

Ten is the *consecutive verified dry-cycle threshold*, never a fixed total
of ten simulations. Every parent sim performs its own primary and checkpoint-
forked shadow run until no **new semantic evidence** is found for ten
consecutive audited cycles, or an explicit finite resource ceiling is hit.
A budget stop is NOT a saturation certificate.

Novelty means a new finite original-game (action, acceptance, state-change
direction, reward-sign, terminal) witness, not a fresh seed/hash/time tick.
Scrutiny escalates based on the peak independently established checks.
The receipts cannot claim complete knowledge of unbounded state spaces.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json

from .game_studio_environment import StudioGameEnvironment, parse_studio_source
from .game_studio_scenario_lab import ANGLES, _lane
from .game_studio_multispectral import audit_simulation, MultispectralAuditError
from .game_learning import GameLearningConfig, GamePolicyLearner
from .game_learning_parallel import GameEnvironmentRequest
from .game_studio_environment import studio_request_tree

SCHEMA="skeleton.game_builder.shadow_saturation.v1"
DRY_CYCLES_REQUIRED=10
MAX_CYCLES_PER_SIM=64
MAX_TOTAL_STEPS=10000
MAX_PARALLEL=4
BASE_SCRUTINY=10
MAX_ADDITIONAL_SCRUTINY=8


class ShadowSaturationError(ValueError):
    """A game fork, evidence receipt or bounded saturation certificate failed."""


def _digest(value):
    try:
        raw=json.dumps(value,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True,allow_nan=False).encode()
    except (TypeError,ValueError,RecursionError) as exc:
        raise ShadowSaturationError("shadow evidence requires finite JSON") from exc
    return sha256(raw).hexdigest()


def _fork(source: dict, primary: dict, angle: str, seed: int,
          steps: int, cycle: int) -> tuple[dict,dict]:
    """Copy a real source-bound intermediate snapshot; branch one command."""
    actions=primary["actions"]
    if not actions:
        raise ShadowSaturationError("cannot clone an unexecuted game")
    prefix_length=min(max(0,len(actions)//2),len(actions)-1)
    prefix=actions[:prefix_length]
    before_source=_digest(source)
    parent=StudioGameEnvironment(source,max_steps=steps)
    clone=StudioGameEnvironment(source,max_steps=steps)
    try:
        parent.reset(seed)
        for command in prefix:
            if parent.done:
                raise ShadowSaturationError("parent checkpoint continued after terminal state")
            parent.step(command)
        snap=parent.snapshot()
        clone.reset(seed)
        clone.restore(snap)
        if clone.snapshot()!=snap:
            raise ShadowSaturationError("shadow clone did not restore parent's exact state")
        original_next=actions[prefix_length]
        alternatives=tuple(action for action in clone.spec.actions
                           if action!=original_next)
        alternate=(alternatives[(cycle+seed)%len(alternatives)]
                   if alternatives else original_next)
        if clone.done:
            raise ShadowSaturationError("cannot branch from terminal parent")
        shadow_step=clone.step(alternate)
        # The episode runner replays the same checkpoint prefix and exact
        # alternative command from its own isolated source environment.
        shadow=_lane(
            source,angle,seed,steps,
            scripted_actions=tuple(prefix)+(alternate,),
        )
        if len(shadow["step_receipts"])<=prefix_length or (
            shadow["step_receipts"][prefix_length]["transition_digest"]
            !=shadow_step.transition_digest
        ):
            raise ShadowSaturationError("clone fork did not match independent source replay")
        if before_source!=_digest(source):
            raise ShadowSaturationError("shadow clone unexpectedly modified original source")
        if prefix_length and (
            snap["transition_digest"]!=
            primary["step_receipts"][prefix_length-1]["transition_digest"]
        ):
            raise ShadowSaturationError("parent's saved prefix does not match original simulation")
        witness={
            "schema_version":"skeleton.game_builder.shadow_fork.v1",
            "fork_at_step":prefix_length,
            "parent_snapshot_digest":snap["digest"],
            "shadow_source_digest":shadow["source_digest"],
            "parent_transition_digest":(
                primary["step_receipts"][prefix_length-1]["transition_digest"]
                if prefix_length else snap["transition_digest"]
            ),
            "parent_next_action":original_next,
            "shadow_alternative_action":alternate,
            "distinct_available_action":bool(alternatives),
            "shadow_fork_transition_digest":shadow_step.transition_digest,
            "same_source_same_checkpoint_verified":True,
            "shadow_mutated_parent_source":before_source!=_digest(source),
        }
        return shadow,{**witness,"digest":_digest(witness)}
    finally:
        parent.close()
        clone.close()


def _scrutiny(source: dict, primary: dict, shadow: dict,
              fork: dict, level: int, *, steps: int) -> list[dict]:
    """Raise scrutiny sensitivity as the strongest previous proof advances."""
    if type(level) is not int or not 1<=level<=MAX_ADDITIONAL_SCRUTINY:
        raise ShadowSaturationError("scrutiny escalation must stay finite")
    audits=(primary["multispectral"],shadow["multispectral"])
    gates=[
        ("both_full_ten_pass_audits",all(
            proof["passed_count"]==10 and proof["failed_count"]==0
            for proof in audits
        )),
        ("fork_snapshot_source_custody",
         fork["same_source_same_checkpoint_verified"] and
         primary["source_digest"]==shadow["source_digest"]==
         fork["shadow_source_digest"]),
        ("source_unchanged_after_fork",not fork["shadow_mutated_parent_source"]),
        ("transition_log_lengths_match",
         all(len(lane["step_receipts"])==lane["steps"]
             for lane in (primary,shadow))),
        ("reverse_checkpoint_receipts_present",
         all(len(proof["reverse_checkpoints"])>=2 for proof in audits)),
        ("finite_reward_and_derived_bands",
         all(proof["spectral_type"]=="derived_multiband_gameplay_telemetry"
             for proof in audits)),
        ("source_bound_shadow_branch",
         shadow["step_receipts"][fork["fork_at_step"]]["action"]==
         fork["shadow_alternative_action"]),
        ("independent_reaudit_on_peak",
         audit_simulation(source,shadow,steps=steps)==
         shadow["multispectral"]),
    ]
    # The first cycle still has its original ten checks on both real runs.
    # Level N always runs the first N extra independent checks as well;
    # the peak never drops on a subsequent cycle.
    selected=gates[:level]
    if not all(ok for _,ok in selected):
        raise ShadowSaturationError("one of the escalating source scrutiny gates failed")
    return [{"name":name,"passed":True} for name,_ in selected]


def _lane_signals(lane: dict) -> set[str]:
    if (lane.get("audit_passed") is not True
            or lane.get("multispectral",{}).get("passed_count")!=10
            or len(lane.get("semantic_behavior_digests",[]))!=lane.get("steps")):
        raise ShadowSaturationError("unknown/unverified game observations cannot be learned")
    result=lane["semantic_behavior_digests"]
    if any(type(token) is not str or len(token)!=64
           or any(ch not in "0123456789abcdef" for ch in token)
           for token in result):
        raise ShadowSaturationError("novelty requires source-derived semantic evidence hashes")
    return set(result)


def _policy_change(before: dict, after: dict) -> tuple[int,float]:
    """Actual sparse Q-state-action coverage plus max source-trained Q delta."""
    first={tuple(row["state"]):row for row in before["q_table"]}
    last={tuple(row["state"]):row for row in after["q_table"]}
    added=0
    delta=0.0
    for key,current in last.items():
        previous=first.get(key)
        original_values=(previous["values"] if previous is not None
                         else [0.0]*len(current["values"]))
        original_visits=(previous["visits"] if previous is not None
                         else [0]*len(current["visits"]))
        for old,new,old_visits,new_visits in zip(
            original_values,current["values"],original_visits,current["visits"]
        ):
            delta=max(delta,abs(float(new)-float(old)))
            added+=int(old_visits==0 and new_visits>0)
    return added,round(delta,9)


def _one(source:dict,angle:str,base_seed:int,steps:int,
         max_cycles:int, dry_cycles:int,
         max_work:int,
         *,on_receipt:Callable[[dict],None]|None=None,
         cancel:Callable[[],bool]|None=None,
         train_policy:bool=False,
         q_change_tolerance:float=0.0001) -> dict:
    learner=None
    request=None
    if train_policy:
        request=GameEnvironmentRequest(
            "studio:"+source["editor"],kind="studio",
            tree=studio_request_tree(source),max_steps=steps,
        )
        probe=request.build()
        try:
            spec=probe.spec
        finally:
            probe.close()
        learner=GamePolicyLearner(
            spec,GameLearningConfig(
                seed=base_seed,max_episodes=max_cycles,
                max_updates=max_cycles*steps,
            ),
            policy_id="shadow:"+source["editor"]+":"+angle+":"+str(base_seed),
            source_lineage={
                "origin":"independent_shadow_saturation_candidate_only",
                "rights_acknowledged":True,
                "source_request_digest":request.digest,
                "active_production_weights_modified":False,
            },
        )
    seen:set[str]=set()
    records=[]
    receipts=[]
    peak=0
    dry=0
    work=0
    total_actions=0
    saturation=False
    stop_reason="cycle_budget_exhausted_unproven"
    chain=_digest({"editor":source["editor"],"angle":angle,
                   "seed":base_seed,"rule":"source_semantic_novelty_v1"})
    for cycle in range(max_cycles):
        if cancel is not None and cancel():
            stop_reason="operator_cancelled_unproven"
            break
        # Conservative source emulator cost includes replay + independent
        # audits + shadow restores; stop BEFORE a cycle could violate cap.
        reserve=6*steps*(steps+1)
        if work+reserve>max_work:
            stop_reason="compute_budget_exhausted_unproven"
            break
        seed=base_seed+cycle*len(ANGLES)
        if seed>2**31-1:
            stop_reason="seed_budget_exhausted_unproven"
            break
        primary=_lane(source,angle,seed,steps)
        shadow,fork=_fork(source,primary,angle,seed,steps,cycle)
        level=min(MAX_ADDITIONAL_SCRUTINY,max(1,peak+1))
        checks=_scrutiny(source,primary,shadow,fork,level,steps=steps)
        peak=max(peak,level)
        fresh=(_lane_signals(primary)|_lane_signals(shadow))-seen
        seen.update(_lane_signals(primary)|_lane_signals(shadow))
        # In candidate-training mode real updates are part of convergence:
        # each original episode consumes one admitted, independently
        # evidenced game seed. A plateau cannot be declared while measured
        # Q coverage/value changes continue beyond the specified tolerance.
        q_new=0
        q_delta=0.0
        q_updates=0
        q_digest=None
        if learner is not None and request is not None:
            q_before=learner.snapshot()
            actual=learner.train(request.build,episodes=1,seeds=[seed])
            q_after=learner.snapshot()
            q_new,q_delta=_policy_change(q_before,q_after)
            q_updates=actual.updates
            q_digest=q_after["snapshot_digest"]
        learning_gain=bool(fresh or q_new>0 or q_delta>q_change_tolerance)
        dry=0 if learning_gain else dry+1
        # Audited replay consumes more than a single visible environment
        # step. Report estimated replayed action applications separately
        # from genuinely executed primary/shadow game actions.
        steps_actual=primary["steps"]+shadow["steps"]
        total_actions+=steps_actual
        expense=(primary["replayed_action_applications"]
                 +shadow["replayed_action_applications"])*3
        work+=expense
        audit={
            "schema_version":"skeleton.game_builder.shadow_cycle_receipt.v1",
            "angle":angle,"cycle":cycle+1,"seed":seed,
            "primary_digest":primary["digest"],
            "shadow_digest":shadow["digest"],
            "primary_multispectral_digest":primary["multispectral"]["digest"],
            "shadow_multispectral_digest":shadow["multispectral"]["digest"],
            "fork":fork,
            "primary_step_receipts":primary["step_receipts"],
            "shadow_step_receipts":shadow["step_receipts"],
            "primary_reverse_checkpoints":primary["multispectral"]["reverse_checkpoints"],
            "shadow_reverse_checkpoints":shadow["multispectral"]["reverse_checkpoints"],
            "escalated_scrutiny_level":level,
            "scrutiny_checks":checks,
            "base_audits_passed":20,
            "additional_checks_passed":len(checks),
            "new_semantic_evidence_count":len(fresh),
            "new_semantic_digests":sorted(fresh),
            "cumulative_semantic_evidence_count":len(seen),
            "new_policy_state_action_pairs":q_new,
            "maximum_measured_q_value_change":q_delta,
            "q_change_tolerance":q_change_tolerance,
            "actual_game_q_updates":q_updates,
            "policy_snapshot_digest":q_digest,
            "real_learning_gain_detected":learning_gain,
            "zero_novelty_streak":dry,
            "completed_cycle_game_steps":steps_actual,
            "cumulative_game_steps":total_actions,
            "estimated_replayed_action_applications":expense,
            "cumulative_estimated_replayed_actions":work,
            "previous_receipt_digest":chain,
            "runtime_proof":"source_executed_twice_and_independently_audited",
            "production_neural_weights_modified":False,
        }
        chain=_digest(audit)
        receipt={**audit,"digest":chain}
        if len(json.dumps(receipt,sort_keys=True,allow_nan=False))>65536:
            raise ShadowSaturationError("one scrutiny cycle exceeds the evidence record budget")
        receipts.append(receipt)
        records.append({
            "cycle":cycle+1,"new_evidence":len(fresh),
            "zero_novelty_streak":dry,
            "peak_additional_scrutiny_checks":peak,
            "receipt_digest":chain,
        })
        if on_receipt is not None:
            on_receipt(deepcopy(receipt))
        if dry>=dry_cycles:
            saturation=True
            stop_reason="ten_consecutive_zero_gain_audited_cycles"
            break
    out={
        "schema_version":"skeleton.game_builder.shadow_sim_result.v1",
        "editor":source["editor"],"angle":angle,
        "source_digest":_digest(source),
        "episode_step_budget":steps,
        "base_seed":base_seed,
        "cycles_executed":len(receipts),
        "total_primary_and_shadow_runs":2*len(receipts),
        "required_consecutive_zero_novelty_cycles":dry_cycles,
        "observed_zero_novelty_streak":dry,
        "saturation_within_tested_bounds":saturation,
        "universal_learning_exhaustion_proven":False,
        "stop_reason":stop_reason,
        "observed_unique_semantic_behaviors":len(seen),
        "peak_additional_scrutiny_checks":peak,
        "peak_total_checks_per_cycle":20+peak,
        "total_game_steps":total_actions,
        "estimated_replayed_action_applications":work,
        "receipts":receipts,
        "receipt_chain_head":chain,
        "candidate_q_training_enabled":train_policy,
        "candidate_q_policy_snapshot":(
            None if learner is None else learner.snapshot()
        ),
        "q_gain_tolerance":q_change_tolerance,
        "production_neural_weights_modified":False,
    }
    if len(json.dumps(out,sort_keys=True,allow_nan=False))>2000000:
        raise ShadowSaturationError("per-simulation receipts exceed finite evidence storage")
    return {**out,"digest":_digest(out)}


def run_shadow_saturation(source:Mapping[str,object], *, seed:int=0,
                          steps:int=4,
                          angles:tuple[str,...]=ANGLES,
                          max_cycles_per_sim:int=24,
                          dry_cycles:int=DRY_CYCLES_REQUIRED,
                          max_replay_work_per_sim:int=10000,
                          workers:int=2,
                          cancel:Callable[[],bool]|None=None,
                          on_receipt:Callable[[dict],None]|None=None,
                          train_policy:bool=False,
                          authorized:bool=False,
                          rights_cleared:bool=False,
                          q_change_tolerance:float=0.0001) -> dict:
    if train_policy and (authorized is not True or rights_cleared is not True):
        raise PermissionError("shadow Q-learning requires actual operator and original-source rights")
    original=parse_studio_source(source)
    if (type(train_policy) is not bool or type(q_change_tolerance) is not float
            or not 1e-9<=q_change_tolerance<=0.1):
        raise ShadowSaturationError("model training switch and Q convergence tolerance must be bounded")
    if (type(seed) is not int or not 0<=seed<=2**31-10000
            or type(steps) is not int or not 1<=steps<=12
            or type(max_cycles_per_sim) is not int
            or not dry_cycles<=max_cycles_per_sim<=MAX_CYCLES_PER_SIM
            or dry_cycles!=DRY_CYCLES_REQUIRED
            or type(max_replay_work_per_sim) is not int
            or not 100<=max_replay_work_per_sim<=MAX_TOTAL_STEPS
            or type(workers) is not int or not 1<=workers<=MAX_PARALLEL
            or type(angles) not in (tuple,list)
            or not 1<=len(angles)<=len(ANGLES)
            or len(set(angles))!=len(angles)
            or any(angle not in ANGLES for angle in angles)):
        raise ShadowSaturationError("finite ten-dry-cycle shadow laboratory admission required")
    def execute(pair):
        index,angle=pair
        return _one(original,angle,seed+index,steps,max_cycles_per_sim,
                    dry_cycles,max_replay_work_per_sim,on_receipt=on_receipt,
                    cancel=cancel,train_policy=train_policy,
                    q_change_tolerance=q_change_tolerance)
    with ThreadPoolExecutor(max_workers=min(workers,len(angles)),
                            thread_name_prefix="jeeves-shadow-saturation") as pool:
        results=list(pool.map(execute,enumerate(angles)))
    outcome={
        "schema_version":SCHEMA,
        "source_editor":original["editor"],
        "angles":list(angles),
        "simulations":results,
        "parent_sim_count":len(results),
        "total_executed_primary_shadow_runs":sum(x["total_primary_and_shadow_runs"] for x in results),
        "actual_game_steps":sum(x["total_game_steps"] for x in results),
        "estimated_replayed_action_applications":sum(
            x["estimated_replayed_action_applications"] for x in results
        ),
        "individual_saturation_verified_count":sum(
            bool(x["saturation_within_tested_bounds"]) for x in results
        ),
        "all_saturated_within_bounds":all(x["saturation_within_tested_bounds"] for x in results),
        "universal_game_knowledge_exhaustion_claimed":False,
        "ten_consecutive_nonproductive_cycles_required":dry_cycles,
        "per_sim_cycle_hard_limit":max_cycles_per_sim,
        "audit_source":"independent_game_replays_and_reverse_checkpoint_proof",
        "candidate_q_training_enabled":train_policy,
        "candidate_q_policy_count":sum(
            x["candidate_q_policy_snapshot"] is not None for x in results
        ),
        "automatic_promotion":False,
        "production_neural_weights_modified":False,
    }
    if len(json.dumps(outcome,sort_keys=True,allow_nan=False))>15000000:
        raise ShadowSaturationError("shadow room exceeds bounded record capacity")
    return {**outcome,"digest":_digest(outcome)}


def verify_shadow_receipts(document:dict, *,
                           source:Mapping[str,object]|None=None) -> bool:
    """Check every log chain; optionally re-execute the complete source again."""
    if type(document) is not dict or document.get("schema_version")!=SCHEMA:
        raise ShadowSaturationError("unknown shadow room receipt schema")
    value={k:v for k,v in document.items() if k!="digest"}
    if _digest(value)!=document.get("digest"):
        raise ShadowSaturationError("overall shadow room digest changed")
    original=parse_studio_source(source) if source is not None else None
    if original is not None and original["editor"]!=document["source_editor"]:
        raise ShadowSaturationError("independent game source identity differs")
    for sim in document["simulations"]:
        payload={k:v for k,v in sim.items() if k!="digest"}
        if original is not None and sim["source_digest"]!=_digest(original):
            raise ShadowSaturationError("saved shadow source differs from independent replay source")
        if _digest(payload)!=sim["digest"]:
            raise ShadowSaturationError("shadow simulation evidence changed")
        previous=_digest({
            "editor":sim["editor"],"angle":sim["angle"],
            "seed":sim["base_seed"],"rule":"source_semantic_novelty_v1",
        })
        seen=set()
        dry=0
        for i,row in enumerate(sim["receipts"]):
            raw={k:v for k,v in row.items() if k!="digest"}
            if (_digest(raw)!=row["digest"] or
                    row["previous_receipt_digest"]!=previous or
                    row["cycle"]!=i+1 or row["base_audits_passed"]!=20
                    or len(row["scrutiny_checks"])!=row["additional_checks_passed"]
                    or not all(c["passed"] is True for c in row["scrutiny_checks"])):
                raise ShadowSaturationError("shadow receipt chain or scrutiny record tampered")
            fresh=set(row["new_semantic_digests"])-seen
            if len(fresh)!=row["new_semantic_evidence_count"] or len(fresh)!=len(row["new_semantic_digests"]):
                raise ShadowSaturationError("false or duplicate knowledge claim")
            seen.update(fresh)
            gain=bool(
                fresh or row["new_policy_state_action_pairs"]>0
                or row["maximum_measured_q_value_change"]>row["q_change_tolerance"]
            )
            if row["real_learning_gain_detected"] is not gain:
                raise ShadowSaturationError("reported knowledge gain disagrees with real evidence")
            dry=0 if gain else dry+1
            if row["zero_novelty_streak"]!=dry:
                raise ShadowSaturationError("stalled-cycle count inconsistent with receipts")
            if original is not None:
                step_budget=sim["episode_step_budget"]
                primary_commands=[x["action"] for x in row["primary_step_receipts"]]
                shadow_commands=[x["action"] for x in row["shadow_step_receipts"]]
                primary=_lane(
                    original,sim["angle"],row["seed"],step_budget,
                    scripted_actions=tuple(primary_commands),
                )
                cloned=_lane(
                    original,sim["angle"],row["seed"],step_budget,
                    scripted_actions=tuple(shadow_commands),
                )
                if (primary["digest"]!=row["primary_digest"]
                    or cloned["digest"]!=row["shadow_digest"]
                    or primary["multispectral"]["digest"]!=row["primary_multispectral_digest"]
                    or cloned["multispectral"]["digest"]!=row["shadow_multispectral_digest"]):
                    raise ShadowSaturationError(
                        "independently rerun original source diverges from persisted cycle"
                    )
                # Reconstruct the actual branching checkpoint again, including
                # its alternative action, rather than trusting a fork label.
                witness,witness_proof=_fork(
                    original,primary,sim["angle"],row["seed"],
                    step_budget,row["cycle"]-1,
                )
                if witness["digest"]!=cloned["digest"] or (
                    witness_proof!=row["fork"]
                ):
                    raise ShadowSaturationError("independent saved shadow fork differs")
            previous=row["digest"]
        if (previous!=sim["receipt_chain_head"] or
                len(seen)!=sim["observed_unique_semantic_behaviors"] or
                dry!=sim["observed_zero_novelty_streak"] or
                bool(dry>=DRY_CYCLES_REQUIRED)!=sim["saturation_within_tested_bounds"]):
            raise ShadowSaturationError("simulated learning-stop claim is not supported by audit history")
    return True


__all__=["DRY_CYCLES_REQUIRED","ShadowSaturationError",
         "run_shadow_saturation","verify_shadow_receipts"]
