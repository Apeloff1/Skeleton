"""Full real native SFT with validation-only selection and candidate-only output.

No test or holdout token becomes a gradient. The source champion stays
immutable; a failure after SGD retains no promoted serving side effect.
"""
from __future__ import annotations
from dataclasses import dataclass
from time import monotonic_ns

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from .bootstrap import AlignedGenesis
from .target_plan import TargetPlan,prepare_targets
from .evaluation_windows import build as evaluation_windows
from .loss import MeasuredLoss,measure_windows
from .optimizer import OptimizerReceipt,execute_epoch
from .quality_threshold import QualityDecision,judge
from .canonical import bytes_sha,digest
from .errors import reject


@dataclass(frozen=True,slots=True)
class EpochResult:
    ordinal:int
    weights_sha256:str
    optimizer_receipt:OptimizerReceipt
    validation_loss:MeasuredLoss
    quality:QualityDecision

    def report(self)->dict:
        return {
            "ordinal":self.ordinal,"weights_sha256":self.weights_sha256,
            "optimizer":self.optimizer_receipt.record(),
            "validation":self.validation_loss.report(),
            "decision":self.quality.report(),
        }


@dataclass(frozen=True,slots=True)
class SupervisedResult:
    genesis:AlignedGenesis
    target_plan:TargetPlan
    initial_validation_loss:MeasuredLoss
    best_validation_loss:MeasuredLoss
    epoch_results:tuple[EpochResult,...]
    candidate_checkpoint:bytes
    candidate_checkpoint_sha256:str
    candidate_model_sha256:str
    tokenizer_sha256:str
    actual_optimizer_steps:int
    elapsed_ms:int
    quality:QualityDecision

    def receipt(self)->dict:
        return {
            "schema":"skeleton.native-supervised.training-receipt.v1",
            "genesis_sha256":self.genesis.runtime.model_digest,
            "initial_checkpoint_sha256":self.genesis.initial_checkpoint_sha256,
            "source_sha256":self.genesis.source.corpus_sha256,
            "training_policy_sha256":self.genesis.policy.sha256,
            "target_plan":self.target_plan.summary(),
            "initial_validation_loss":self.initial_validation_loss.report(),
            "best_validation_loss":self.best_validation_loss.report(),
            "epochs":[e.report() for e in self.epoch_results],
            "candidate_checkpoint_sha256":self.candidate_checkpoint_sha256,
            "candidate_model_sha256":self.candidate_model_sha256,
            "candidate_tokenizer_sha256":self.tokenizer_sha256,
            "optimizer_steps":self.actual_optimizer_steps,
            "elapsed_ms":self.elapsed_ms,
            "real_native_completion_sgd":True,
            "candidate_only":True,
            "production_authorized":False,
            "challenge_accuracy_verified":False,
            "release_certified":False,
        }


def train(instance:AlignedGenesis)->SupervisedResult:
    if type(instance) is not AlignedGenesis:
        reject("train-aligned-genesis")
    policy=instance.policy
    instance.runtime.assert_model_unchanged()
    source_model_sha=instance.runtime.model_digest
    # A deserialized model is a new object. No SGD touches the champion.
    model_runtime=NativeLLMRuntime.restore_json(instance.initial_checkpoint.decode("utf-8"))
    if model_runtime.model_digest!=source_model_sha:
        reject("train-initial-clone-identity")
    model=model_runtime.model
    if model.steps!=0:
        reject("train-seed-not-fresh")
    plan=prepare_targets(instance)
    validation=evaluation_windows(model,instance.source,partition="validation")
    if not validation.windows:
        reject("train-no-validation")
    initial=measure_windows(model,validation.windows)
    best=initial
    best_bytes=None
    best_model_sha=None
    results=[]
    started=monotonic_ns()
    actual_steps=0
    for epoch in range(policy.epochs):
        receipt=execute_epoch(
            model,plan.windows,epoch=epoch,total_epochs=policy.epochs,
            global_step_start=actual_steps,total_steps=plan.total_optimizer_steps,
            learning_rate_ppm=policy.learning_rate_ppm,
            max_wall_ms=policy.max_wall_ms,start_monotonic_ns=started,
            batch_size=policy.batch_examples,
        )
        actual_steps+=receipt.steps
        current_runtime=NativeLLMRuntime(model)
        measured=measure_windows(current_runtime.model,validation.windows)
        decision=judge(initial,measured,policy)
        results.append(EpochResult(
            epoch,current_runtime.model_digest,receipt,measured,decision,
        ))
        if decision.eligible_for_independent_probes and measured.loss_ppm < best.loss_ppm:
            encoded=current_runtime.checkpoint_json().encode("utf-8")
            if len(encoded)>policy.max_checkpoint_bytes:
                reject("train-candidate-storage-budget")
            best_bytes=encoded
            best_model_sha=current_runtime.model_digest
            best=measured
        if (monotonic_ns()-started)//1000000>policy.max_wall_ms:
            reject("train-wall-budget")
    if actual_steps!=plan.total_optimizer_steps:
        reject("train-optimizer-steps")
    if not best_bytes or not best_model_sha:
        reject("train-no-qualified-validation-improvement")
    if best_model_sha==source_model_sha:
        reject("train-no-weight-change")
    restored=NativeLLMRuntime.restore_json(best_bytes.decode("utf-8"))
    if restored.model_digest!=best_model_sha:
        reject("train-best-checkpoint-identity")
    if restored.tokenizer.digest!=instance.runtime.tokenizer.digest:
        reject("train-tokenizer-drift")
    instance.runtime.assert_model_unchanged()
    return SupervisedResult(
        instance,plan,initial,best,tuple(results),
        best_bytes,bytes_sha(best_bytes),best_model_sha,
        restored.tokenizer.digest,actual_steps,
        (monotonic_ns()-started)//1000000,
        judge(initial,best,policy),
    )
