"""Independent promotion, runtime admission, and rollback proof chain."""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.ai.training.flgb_training_runtime import CandidateWeights, MirrorEvaluation, PromotionEvidence, digest_json, require_digest, require_id
from skeleton.ai.training.lifecycle_proof import LifecycleProof, LifecycleStage, LifecycleProofError

@dataclass(frozen=True)
class RuntimeAdmission:
    candidate_digest:str
    prior_model_digest:str
    admitted_model_digest:str
    checkpoint_digest:str
    admission_authority:str
    atomic:bool
    def __post_init__(self):
        for n in ("candidate_digest","prior_model_digest","admitted_model_digest","checkpoint_digest"): require_digest(getattr(self,n),n)
        require_id(self.admission_authority,"admission_authority")
        if self.atomic is not True: raise LifecycleProofError("runtime admission must be atomic")
    @property
    def digest(self): return digest_json(self.__dict__)

@dataclass(frozen=True)
class RollbackProof:
    admission_digest:str
    checkpoint_digest:str
    restored_model_digest:str
    verifier_id:str
    verified:bool
    executed:bool=False
    def __post_init__(self):
        for n in ("admission_digest","checkpoint_digest","restored_model_digest"): require_digest(getattr(self,n),n)
        require_id(self.verifier_id,"verifier_id")
        if not isinstance(self.verified,bool) or not isinstance(self.executed,bool): raise LifecycleProofError("rollback flags must be boolean")
    @property
    def digest(self): return digest_json(self.__dict__)

def extend_with_promotion(
    proof:LifecycleProof,candidate:CandidateWeights,evaluation:MirrorEvaluation,promotion:PromotionEvidence,
    admission:RuntimeAdmission,rollback:RollbackProof,
)->LifecycleProof:
    if candidate.status not in {"candidate","promoted"}: raise LifecycleProofError("candidate not eligible")
    if proof.stages[-1].stage != "candidate-training-run" or candidate.training_lineage_digest != proof.stages[-1].subject_digest:
        raise LifecycleProofError("candidate training lineage does not match proven run")
    if admission.prior_model_digest != candidate.base_model_digest:
        raise LifecycleProofError("runtime prior model does not match candidate base model")
    if evaluation.champion_digest != candidate.base_model_digest:
        raise LifecycleProofError("evaluation champion does not match candidate base model")
    if evaluation.candidate_digest!=candidate.digest: raise LifecycleProofError("evaluation/candidate mismatch")
    if not evaluation.candidate_wins: raise LifecycleProofError("independent evaluation did not select candidate")
    if promotion.candidate_digest!=candidate.digest or promotion.evaluation_digest!=digest_json(evaluation.__dict__): raise LifecycleProofError("promotion evidence identity mismatch")
    if not promotion.qualified: raise LifecycleProofError("promotion evidence not qualified")
    if evaluation.independent_verifier!=promotion.independent_verifier: raise LifecycleProofError("evaluation/promotion verifier mismatch")
    if admission.candidate_digest!=candidate.digest: raise LifecycleProofError("runtime admission candidate mismatch")
    if admission.admitted_model_digest!=candidate.weights_digest: raise LifecycleProofError("runtime model does not equal candidate weights")
    if promotion.rollback_digest!=admission.checkpoint_digest: raise LifecycleProofError("promotion rollback checkpoint mismatch")
    if rollback.admission_digest!=admission.digest or rollback.checkpoint_digest!=admission.checkpoint_digest: raise LifecycleProofError("rollback/admission mismatch")
    if not rollback.verified or rollback.restored_model_digest!=admission.prior_model_digest: raise LifecycleProofError("rollback is not proven ready for prior model")
    if evaluation.independent_verifier==admission.admission_authority: raise LifecycleProofError("evaluation and runtime admission authorities must be separate")
    if rollback.verifier_id in {evaluation.independent_verifier,admission.admission_authority}: raise LifecycleProofError("rollback verifier must be independent")
    prev=proof.stages[-1].digest
    extra=(
      LifecycleStage("candidate-weights",candidate.digest,candidate.training_lineage_digest,prev),
      LifecycleStage("independent-mirror-evaluation",evaluation.candidate_digest,digest_json(evaluation.__dict__),None),
      LifecycleStage("qualified-promotion",promotion.candidate_digest,promotion.digest,None),
      LifecycleStage("atomic-runtime-admission",admission.admitted_model_digest,admission.digest,None),
      LifecycleStage("rollback-executed" if rollback.executed else "rollback-ready",rollback.restored_model_digest,rollback.digest,None),
    )
    linked=[]; p=prev
    for s in extra:
      s=LifecycleStage(s.stage,s.subject_digest,s.authority_digest,p); linked.append(s); p=s.digest
    return LifecycleProof(proof.lifecycle_id,proof.stages+tuple(linked))

__all__=["RuntimeAdmission","RollbackProof","extend_with_promotion"]
