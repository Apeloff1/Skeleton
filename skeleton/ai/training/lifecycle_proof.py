"""Proof-carrying lifecycle chain for governed AI self-improvement."""
from __future__ import annotations
from dataclasses import dataclass
from .flgb_training_runtime import digest_json, require_digest, require_id
from .project_learning import ProjectOutcome, LearningApproval, ProjectTrainingAdmission
from .project_learning_run import ProjectLearningRun

class LifecycleProofError(ValueError): pass

@dataclass(frozen=True)
class LifecycleStage:
    stage:str
    subject_digest:str
    authority_digest:str
    previous_digest:str|None
    def __post_init__(self):
        require_id(self.stage,"stage"); require_digest(self.subject_digest,"subject_digest")
        require_digest(self.authority_digest,"authority_digest")
        if self.previous_digest is not None: require_digest(self.previous_digest,"previous_digest")
    @property
    def digest(self): return digest_json({"schema":"skeleton.ai.lifecycle-stage.v1",**self.__dict__})

@dataclass(frozen=True)
class LifecycleProof:
    lifecycle_id:str
    stages:tuple[LifecycleStage,...]
    def __post_init__(self):
        require_id(self.lifecycle_id,"lifecycle_id")
        if not self.stages: raise LifecycleProofError("lifecycle proof requires stages")
        seen=set()
        for i,s in enumerate(self.stages):
            if s.digest in seen: raise LifecycleProofError("replayed lifecycle stage")
            seen.add(s.digest)
            expected=None if i==0 else self.stages[i-1].digest
            if s.previous_digest!=expected: raise LifecycleProofError("broken lifecycle chain")
    @property
    def digest(self): return digest_json({"schema":"skeleton.ai.lifecycle-proof.v1","lifecycle_id":self.lifecycle_id,"stage_digests":[s.digest for s in self.stages]})

def prove_project_learning(lifecycle_id:str,outcome:ProjectOutcome,approval:LearningApproval,admission:ProjectTrainingAdmission,run:ProjectLearningRun)->LifecycleProof:
    if outcome.status!="successful": raise LifecycleProofError("lifecycle outcome not successful")
    if approval.outcome_digest!=outcome.digest or not approval.approved: raise LifecycleProofError("learning approval is not bound and affirmative")
    if admission.outcome_digest!=outcome.digest or admission.approval_digest!=approval.digest: raise LifecycleProofError("training admission identity substitution")
    if run.admission_digest!=admission.digest: raise LifecycleProofError("training run/admission mismatch")
    if run.manifest.output_kind!="candidate-only": raise LifecycleProofError("training authority escalated beyond candidate")
    s1=LifecycleStage("successful-project-outcome",outcome.digest,outcome.success_evidence_digest,None)
    s2=LifecycleStage("explicit-learning-approval",approval.outcome_digest,approval.digest,s1.digest)
    s3=LifecycleStage("dataset-admission",admission.revision.digest,admission.digest,s2.digest)
    s4=LifecycleStage("candidate-training-run",run.manifest.digest,run.admission_digest,s3.digest)
    return LifecycleProof(lifecycle_id,(s1,s2,s3,s4))

__all__=["LifecycleProofError","LifecycleStage","LifecycleProof","prove_project_learning"]
