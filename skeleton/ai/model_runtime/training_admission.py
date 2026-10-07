"""Atomic promoted-candidate admission bound to the native runtime's observed state."""
from __future__ import annotations
from typing import Callable
from skeleton.ai.training.flgb_training_runtime import CandidateWeights, PromotionEvidence
from skeleton.ai.training.promotion_lifecycle import RuntimeAdmission, RollbackProof
from .native_llm_runtime import NativeLLMRuntime

class RuntimePromotionError(ValueError): pass

def _restore_in_place(runtime:NativeLLMRuntime, checkpoint:object, prior_digest:str)->None:
    restored=NativeLLMRuntime.restore(checkpoint,device_policy=runtime.device_policy)
    runtime.model=restored.model
    runtime.limits=restored.limits
    runtime.device_policy=restored.device_policy
    runtime._model_snapshot=restored._model_snapshot
    runtime._model_digest=restored._model_digest
    runtime._model_bytes=restored._model_bytes
    runtime.tokenizer=restored.tokenizer
    runtime.architecture=restored.architecture
    runtime.device=restored.device
    if runtime.model_digest!=prior_digest: raise RuntimePromotionError("in-place rollback failed")

def admit_candidate_model(
    runtime:NativeLLMRuntime,
    candidate:CandidateWeights,
    promotion:PromotionEvidence,
    apply_candidate:Callable[[object],None],
    *,
    admission_authority:str,
)->tuple[NativeLLMRuntime,RuntimeAdmission,RollbackProof]:
    if not isinstance(runtime,NativeLLMRuntime): raise RuntimePromotionError("NativeLLMRuntime required")
    if not isinstance(candidate,CandidateWeights) or not isinstance(promotion,PromotionEvidence): raise RuntimePromotionError("typed candidate and promotion evidence required")
    if candidate.status not in {"candidate","promoted"}: raise RuntimePromotionError("candidate not admissible")
    if promotion.candidate_digest!=candidate.digest or not promotion.qualified: raise RuntimePromotionError("candidate lacks qualified promotion")
    checkpoint=runtime.checkpoint()
    prior=runtime.model_digest
    if checkpoint["model_digest"]!=prior: raise RuntimePromotionError("checkpoint/runtime identity mismatch")
    if checkpoint["digest"]!=promotion.rollback_digest: raise RuntimePromotionError("promotion did not authorize this rollback checkpoint")
    try:
        apply_candidate(runtime.model)
        observed=runtime.refresh_model_identity()
        if observed!=candidate.weights_digest: raise RuntimePromotionError("observed candidate weights do not match declared digest")
        if observed==prior: raise RuntimePromotionError("candidate did not change model identity")
    except Exception:
        _restore_in_place(runtime,checkpoint,prior)
        raise
    admission=RuntimeAdmission(candidate.digest,prior,observed,checkpoint["digest"],admission_authority,True)
    restored=NativeLLMRuntime.restore(checkpoint,device_policy=runtime.device_policy)
    if restored.model_digest!=prior: raise RuntimePromotionError("rollback verification failed")
    rollback=RollbackProof(admission.digest,checkpoint["digest"],restored.model_digest,"native-runtime-restore",True)
    return runtime,admission,rollback

__all__=["RuntimePromotionError","admit_candidate_model"]
