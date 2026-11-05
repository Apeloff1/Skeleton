"""Assert that only response targets received gradient supervision."""
from __future__ import annotations
from .target_plan import TargetPlan
from .training_separation import prove
from .trainer import SupervisedResult
from .errors import reject


def verify(result:SupervisedResult)->dict:
    if type(result) is not SupervisedResult:
        reject("completion-guard-result")
    separation=prove(result.target_plan,result.genesis.source)
    if result.actual_optimizer_steps!=result.target_plan.total_optimizer_steps:
        reject("completion-gradient-count")
    if not result.quality.eligible_for_independent_probes:
        reject("completion-no-positive-validation")
    if any(r.optimizer_receipt.steps!=result.target_plan.steps_per_epoch
           for r in result.epoch_results):
        reject("completion-epoch-missing")
    return {
        "schema":"skeleton.native-supervised.completion-guard.v1",
        **separation,
        "real_native_sgd_steps":result.actual_optimizer_steps,
        "trained_on_prompt_tokens":False,
        "trained_on_holdout":False,
        "candidate_only":True,
        "release_certified":False,
    }
