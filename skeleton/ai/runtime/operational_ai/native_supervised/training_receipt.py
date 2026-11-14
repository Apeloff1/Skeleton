"""Independent proof that emitted candidate bytes match actual SGD lineage."""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from .trainer import SupervisedResult
from .canonical import bytes_sha,digest,require_sha
from .errors import reject


@dataclass(frozen=True,slots=True)
class TrainingProof:
    model_sha256:str
    tokenizer_sha256:str
    checkpoint_sha256:str
    source_sha256:str
    target_plan_sha256:str
    epoch_chain_sha256:str
    actual_steps:int
    validation_delta_ppm:int

    def record(self)->dict:
        return {
            "schema":"skeleton.native-supervised.independent-training-proof.v1",
            **{k:getattr(self,k) for k in self.__dataclass_fields__},
            "native_supervised_gradient":True,
            "serving_activated":False,"release_certified":False,
        }


def verify(result:SupervisedResult)->TrainingProof:
    if type(result) is not SupervisedResult:
        reject("training-proof-result")
    data=result.candidate_checkpoint
    if bytes_sha(data)!=result.candidate_checkpoint_sha256:
        reject("training-proof-checkpoint-hash")
    runtime=NativeLLMRuntime.restore_json(data.decode("utf-8"))
    if runtime.model_digest!=result.candidate_model_sha256:
        reject("training-proof-model-identity")
    if runtime.tokenizer.digest!=result.tokenizer_sha256:
        reject("training-proof-tokenizer")
    if runtime.model_digest==result.genesis.runtime.model_digest:
        reject("training-proof-unchanged-model")
    if sum(x.optimizer_receipt.steps for x in result.epoch_results)!=result.actual_optimizer_steps:
        reject("training-proof-steps")
    if not result.quality.eligible_for_independent_probes:
        reject("training-proof-no-validation")
    if len(result.epoch_results)!=result.genesis.policy.epochs:
        reject("training-proof-incomplete-epochs")
    return TrainingProof(
        runtime.model_digest,runtime.tokenizer.digest,
        result.candidate_checkpoint_sha256,result.genesis.source.corpus_sha256,
        result.target_plan.plan_sha256,
        digest([x.report() for x in result.epoch_results]),
        result.actual_optimizer_steps,result.quality.delta_ppm,
    )
