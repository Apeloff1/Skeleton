"""Atomic promoted-candidate admission bound to observed native runtime state."""
from __future__ import annotations
from typing import Callable
from skeleton.ai.training.flgb_training_runtime import CandidateWeights, PromotionEvidence, digest_json, require_digest, require_id
from skeleton.ai.training.promotion_lifecycle import RuntimeAdmission, RollbackProof
from skeleton.ai.training.temporal_admission import TemporalTrainingAdmission
from .native_llm_runtime import NativeLLMRuntime
from .runtime_checkpoint import validate_checkpoint

class RuntimePromotionError(ValueError): pass

class AdmissionLedger:
    """Process-local replay guard; persist signed snapshot before cross-process use."""

    def __init__(self, promotions=(), admissions=()):
        from threading import RLock
        promotions = tuple(promotions)
        admissions = tuple(admissions)
        for name, values in (("promotions", promotions), ("admissions", admissions)):
            if len(values) != len(set(values)):
                raise RuntimePromotionError(f"duplicate {name} receipt")
            for value in values:
                self._require_digest(value, name)
        self._lock = RLock()
        self._promotion_digests = set(promotions)
        self._admission_digests = set(admissions)

    @staticmethod
    def _require_digest(value, label):
        if (not isinstance(value, str) or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)):
            raise RuntimePromotionError(f"invalid {label} receipt digest")

    def reserve_promotion(self, digest):
        self._require_digest(digest, "promotion")
        with self._lock:
            if digest in self._promotion_digests:
                raise RuntimePromotionError("promotion receipt already consumed")
            self._promotion_digests.add(digest)

    def release_promotion(self, digest):
        self._require_digest(digest, "promotion")
        with self._lock:
            self._promotion_digests.discard(digest)

    def record_admission(self, digest):
        self._require_digest(digest, "admission")
        with self._lock:
            if digest in self._admission_digests:
                raise RuntimePromotionError("admission receipt already recorded")
            self._admission_digests.add(digest)

    def snapshot(self):
        with self._lock:
            body = {
                "schema": "skeleton.ai.admission-ledger.v1",
                "promotions": sorted(self._promotion_digests),
                "admissions": sorted(self._admission_digests),
            }
        return {**body, "digest": digest_json(body)}

    @classmethod
    def restore(cls, snapshot):
        if not isinstance(snapshot, dict) or set(snapshot) != {
            "schema", "promotions", "admissions", "digest"
        }:
            raise RuntimePromotionError("invalid admission ledger snapshot")
        body = {k: snapshot[k] for k in ("schema", "promotions", "admissions")}
        if (body["schema"] != "skeleton.ai.admission-ledger.v1"
                or not isinstance(body["promotions"], list)
                or not isinstance(body["admissions"], list)
                or body["promotions"] != sorted(set(body["promotions"]))
                or body["admissions"] != sorted(set(body["admissions"]))
                or snapshot.get("digest") != digest_json(body)):
            raise RuntimePromotionError("invalid admission ledger snapshot")
        return cls(body["promotions"], body["admissions"])

def _restore_in_place(runtime,checkpoint,prior):
    restored=NativeLLMRuntime.restore(checkpoint,device_policy=runtime.device_policy)
    for name in ("model","limits","device_policy","_model_snapshot","_model_digest","_model_bytes","tokenizer","architecture","device"):
        setattr(runtime,name,getattr(restored,name))
    if runtime.model_digest!=prior or runtime._current_model_digest()!=prior: raise RuntimePromotionError("in-place rollback failed")

def admit_candidate_model(runtime:NativeLLMRuntime,candidate:CandidateWeights,promotion:PromotionEvidence,apply_candidate:Callable[[object],None],*,admission_authority:str,ledger:AdmissionLedger|None=None,temporal_admission:TemporalTrainingAdmission|None=None):
    if not isinstance(runtime,NativeLLMRuntime): raise RuntimePromotionError("NativeLLMRuntime required")
    if not isinstance(candidate,CandidateWeights) or not isinstance(promotion,PromotionEvidence): raise RuntimePromotionError("typed candidate and promotion evidence required")
    if candidate.status not in {"candidate","promoted"}: raise RuntimePromotionError("candidate not admissible")
    if candidate.base_model_digest!=runtime.model_digest: raise RuntimePromotionError("candidate base model does not match active runtime")
    if promotion.candidate_digest!=candidate.digest or not promotion.qualified: raise RuntimePromotionError("candidate lacks qualified promotion")
    if temporal_admission is not None:
        if not isinstance(temporal_admission,TemporalTrainingAdmission): raise RuntimePromotionError("typed temporal training admission required")
        if temporal_admission.base_model_digest!=candidate.base_model_digest: raise RuntimePromotionError("temporal admission base model mismatch")
        if temporal_admission.exact_head_commit!=promotion.exact_head_commit: raise RuntimePromotionError("temporal admission exact-head mismatch")
        if temporal_admission.dataset_digest!=candidate.training_lineage_digest: raise RuntimePromotionError("temporal admission training lineage mismatch")
    require_id(admission_authority,"admission_authority")
    if promotion.independent_verifier==admission_authority: raise RuntimePromotionError("evaluation and admission authorities must be separate")
    if ledger is not None: ledger.reserve_promotion(promotion.digest)
    checkpoint=runtime.checkpoint(); prior=runtime.model_digest
    try:
        if checkpoint["model_digest"]!=prior or checkpoint["digest"]!=promotion.rollback_digest: raise RuntimePromotionError("checkpoint not authorized by promotion")
        apply_candidate(runtime.model); observed=runtime.refresh_model_identity()
        if observed!=candidate.weights_digest or observed==prior: raise RuntimePromotionError("observed candidate weights do not match declared digest")
        admission=RuntimeAdmission(candidate.digest,prior,observed,checkpoint["digest"],admission_authority,True)
        if ledger is not None: ledger.record_admission(admission.digest)
    except Exception:
        _restore_in_place(runtime,checkpoint,prior)
        if ledger is not None: ledger.release_promotion(promotion.digest)
        raise
    restored=NativeLLMRuntime.restore(checkpoint,device_policy=runtime.device_policy)
    if restored.model_digest!=prior: raise RuntimePromotionError("rollback verification failed")
    return runtime,admission,RollbackProof(admission.digest,checkpoint["digest"],prior,"native-runtime-restore",True,False)

def execute_rollback(runtime,admission,rollback,checkpoint,*,verifier_id=None):
    body=validate_checkpoint(checkpoint)
    if checkpoint.get("digest")!=admission.checkpoint_digest or checkpoint.get("digest")!=rollback.checkpoint_digest: raise RuntimePromotionError("rollback checkpoint identity mismatch")
    if body["model_digest"]!=admission.prior_model_digest: raise RuntimePromotionError("rollback checkpoint model mismatch")
    verifier_id=verifier_id or rollback.verifier_id
    require_id(verifier_id,"rollback_verifier")
    if verifier_id==admission.admission_authority: raise RuntimePromotionError("rollback verifier must differ from admission authority")
    if rollback.executed: raise RuntimePromotionError("rollback receipt already executed")
    if runtime.model_digest!=admission.admitted_model_digest or runtime._current_model_digest()!=admission.admitted_model_digest: raise RuntimePromotionError("runtime no longer matches admitted model")
    if rollback.admission_digest!=admission.digest or rollback.checkpoint_digest!=admission.checkpoint_digest or not rollback.verified: raise RuntimePromotionError("rollback authority mismatch")
    _restore_in_place(runtime,checkpoint,admission.prior_model_digest)
    return RollbackProof(admission.digest,admission.checkpoint_digest,runtime.model_digest,verifier_id,True,True)

__all__=["RuntimePromotionError","AdmissionLedger","admit_candidate_model","execute_rollback"]
