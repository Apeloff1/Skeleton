"""B039 real quest trace repair with B038 provenance and full-SHA evidence.

The only proposer is a deterministic route-to-active-objective algorithm.
It never executes a model, calls a provider, relaxes policy, edits source
files or turns a failed source check into a passed result.
"""
from __future__ import annotations

from copy import deepcopy
import time

from skeleton.app.recovered_evidence import EvidenceError, array, fields, integer, digest, seal, verify, pin
from skeleton.ai.game_builder.synthesized_quest_runtime import Campaign
from skeleton.ai.game_builder.quest_trace_evaluator import (
    TraceEvaluator,MAX_REPAIR_ACTIONS,MAX_CANDIDATES,
)
from skeleton.gameforge.batch_b039.self_repair import (
    Budget,Mutation,RepairLoop,RouteChoice,
)
from skeleton.gameforge.batch_b038.provenance import (
    GenerationProvenance,ProvenanceLedger,SourceRef,Transformation,EvalRecord,
)

SCHEMA="skeleton.quest-trace-repair.order.v1"
REPORT="skeleton.quest-trace-repair.report.v1"


def _proposer(evaluator,chunk):
    def propose(artifact,diagnoses,route):
        obs=evaluator.observe(artifact)
        if obs.passed:
            return None
        actions=artifact["actions"]
        # Remove only an invalid suffix. A completed prefix with trailing
        # actions is valid once the trailing actions are removed.
        if obs.accepted_prefix<len(actions):
            return Mutation("actions",{"actions":deepcopy(actions[:obs.accepted_prefix])},
                            0.0,"discard invalid suffix")
        # An explicit abandon is user intent. Never erase it or resurrect a
        # terminal failed campaign merely to improve an evaluation score.
        if obs.run.runtime.status=="failed":
            return None
        try:
            suffix=evaluator.proposed_suffix(obs)
        except ValueError:
            return None
        if not suffix:
            return None
        # Cut at an objective boundary whenever possible, so accepted
        # mutations can produce measurable canonical progression.
        stop=min(len(suffix),chunk)
        completions=[i+1 for i,a in enumerate(suffix[:stop]) if a["op"]=="complete"]
        if completions:
            stop=completions[-1]
        replacement=deepcopy(actions)+deepcopy(suffix[:stop])
        if len(replacement)>MAX_REPAIR_ACTIONS:
            return None
        return Mutation("actions",{"actions":replacement},0.0,"append bounded canonical route")
    return propose


def _record_ledger(order,original,artifact,outcome,observations,final):
    ledger=ProvenanceLedger()
    original_sha=digest(original)
    final_sha=digest(artifact)
    # Legacy B039 has 16-character digests. Preserve them in their native
    # fields, but bind full SHA-256 of every evaluated candidate separately.
    source=SourceRef("quest-plan","immutable-canonical-plan",order["expected_plan_digest"])
    transforms=() if original_sha==final_sha else (
        Transformation("verified_trace_repair",original_sha,final_sha,
                       "accepted action trace; source and policy unchanged"),
    )
    record=GenerationProvenance(
        artifact_id=order["campaign"]["campaign_id"]+".trace",
        artifact_digest=final_sha,model="deterministic-route-planner",
        provider="local-stdlib",input_digest=original_sha,
        parameters={"max_mutations":order["max_mutations"],
                    "max_seconds":order["max_seconds"],"chunk_actions":order["chunk_actions"],
                    "candidate_observation_digest":digest(observations),
                    "no_model_invoked":True},
        sources=(source,),transformations=transforms,
        evals=(EvalRecord("canonical_quest_replay",final.result.score,final.passed,
                          "Actual canonical state transition replay"),),
        steps=tuple(outcome.provenance),
    )
    ledger.append(record)
    entries=ledger.entries()
    if not ProvenanceLedger.verify(entries):
        raise EvidenceError("canonical provenance ledger verification failed")
    return {"head":ledger.head,"entries":entries}


def repair_trace(order,*,authorized):
    if authorized is not True:
        raise PermissionError("explicit trace repair operator required")
    fields(order,{"schema","campaign","plan","expected_plan_digest","trace",
                  "max_mutations","max_seconds","chunk_actions"})
    if order["schema"]!=SCHEMA:
        raise EvidenceError("unsupported repair order")
    mutations=integer(order["max_mutations"],0,12)
    seconds=integer(order["max_seconds"],1,120)
    chunk=integer(order["chunk_actions"],1,128)
    original={"actions":deepcopy(array(order["trace"],0,MAX_REPAIR_ACTIONS))}
    evaluator=TraceEvaluator(order["campaign"],order["plan"],order["expected_plan_digest"])
    start=time.monotonic()
    loop=RepairLoop(evaluator.evaluate,_proposer(evaluator,chunk),
                    lambda _:RouteChoice("deterministic-route-planner","local-stdlib",0.0),
                    Budget(mutations,float(seconds),0.0),time.monotonic,patience=2)
    outcome=loop.run(original)
    elapsed=time.monotonic()-start
    artifact=deepcopy(dict(outcome.artifact))
    final=evaluator.observe(artifact)
    elapsed=time.monotonic()-start
    if elapsed>seconds:
        # A synchronous callback cannot be forcibly interrupted. A result
        # arriving after the deadline is held even if gameplay now passes.
        eligible=False
        state="held_time_budget"
    else:
        eligible=final.passed and outcome.status in ("repaired","already_passing")
        state=outcome.status if eligible else "held_"+outcome.status
    ledger=_record_ledger(order,original,artifact,outcome,evaluator.observations,final)
    snapshot=final.run.snapshot()
    if eligible:
        restored=Campaign.restore(order["campaign"],order["plan"],snapshot,
                                  expected_plan_digest=order["expected_plan_digest"],
                                  expected_save_digest=snapshot["digest"],authorized=True)
        if restored.snapshot()!=snapshot or restored.runtime.status!="completed":
            raise EvidenceError("final independent replay differs")
    elapsed=time.monotonic()-start
    if elapsed>seconds:
        eligible=False
        state="held_time_budget"
    return seal({"schema":REPORT,"order_digest":digest(order),
                 "plan_digest":order["expected_plan_digest"],"original_trace_digest":digest(original),
                 "candidate_trace":artifact["actions"],"candidate_trace_digest":digest(artifact),
                 "candidate_status":snapshot["status"],"candidate_snapshot_digest":snapshot["digest"],
                 "status":state,"eligible_for_human_review":eligible,
                 "mutation_count":outcome.steps,"maximum_mutations":mutations,
                 "case_evaluations":evaluator.calls,"evaluated_action_ceiling":evaluator.attempted_actions,
                 "candidate_observations":evaluator.observations,"provenance":ledger,
                 "source_policy_unchanged":True,"measured_elapsed_ms":int(elapsed*1000),
                 "hard_preemption":False,"local_model_invoked":False,"provider_invoked":False,
                 "writes_authorized":False,"native_engine_executed":False,"release_certified":False})
