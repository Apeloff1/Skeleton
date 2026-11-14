"""Verify optimizer updated response windows only with source-bound step counts."""
from __future__ import annotations
from .trainer import SupervisedResult
from .training_separation import prove
from .receipt_chain import build,verify
from .canonical import digest
from .errors import reject


def audit(result:SupervisedResult)->dict:
    if type(result) is not SupervisedResult:
        reject("gradient-result")
    isolation=prove(result.target_plan,result.genesis.source)
    chain=build(result.epoch_results)
    proof=verify(chain,result.epoch_results)
    if result.actual_optimizer_steps!=result.target_plan.total_optimizer_steps:
        reject("gradient-receipt-step-total")
    if any(x.optimizer_receipt.steps!=result.target_plan.steps_per_epoch
           for x in result.epoch_results):
        reject("gradient-epoch-steps")
    return {
        "schema":"skeleton.native-supervised.gradient-audit.v1",
        "isolation":isolation,
        "chain":proof,
        "actual_optimizer_steps":result.actual_optimizer_steps,
        "expected_optimizer_steps":result.target_plan.total_optimizer_steps,
        "training_evidence_sha256":digest(result.receipt()),
        "prompt_gradient_targets":0,
        "holdout_gradient_targets":0,
        "champion_mutated":False,
        "model_release_authorized":False,
    }
