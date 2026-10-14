"""Explicit approval boundary from successful project outcomes to FLGB-07 datasets."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

from .flgb_training_runtime import DatasetRevision, DatasetRights, TrainingContractError, digest_json, require_digest, require_id

class ProjectLearningError(TrainingContractError): pass

@dataclass(frozen=True)
class ProjectOutcome:
    outcome_id:str
    tenant_id:str
    project_id:str
    knowledge_root_digest:str
    model_identity_digest:str
    output_digest:str
    replay_receipt_digest:str
    content_digest:str
    success_evidence_digest:str
    status:str
    def __post_init__(self):
        for n in ("outcome_id","tenant_id","project_id"): require_id(getattr(self,n),n)
        for n in ("knowledge_root_digest","model_identity_digest","output_digest","replay_receipt_digest","content_digest","success_evidence_digest"): require_digest(getattr(self,n),n)
        if self.status not in {"candidate","successful","rejected"}: raise ProjectLearningError("invalid outcome status")
    @property
    def digest(self): return digest_json(self.__dict__)

@dataclass(frozen=True)
class LearningApproval:
    outcome_digest:str
    approver_id:str
    rights_evidence_digest:str
    contamination_scan_digest:str
    transform_digest:str
    scope:str
    approved:bool
    def __post_init__(self):
        require_digest(self.outcome_digest,"outcome_digest"); require_id(self.approver_id,"approver_id")
        require_digest(self.rights_evidence_digest,"rights_evidence_digest")
        require_digest(self.contamination_scan_digest,"contamination_scan_digest")
        require_digest(self.transform_digest,"transform_digest"); require_id(self.scope,"scope")
        if not isinstance(self.approved,bool): raise ProjectLearningError("approved must be boolean")
    @property
    def digest(self): return digest_json(self.__dict__)

@dataclass(frozen=True)
class ProjectTrainingAdmission:
    rights:DatasetRights
    revision:DatasetRevision
    outcome_digest:str
    approval_digest:str
    def __post_init__(self):
        require_digest(self.outcome_digest,"outcome_digest"); require_digest(self.approval_digest,"approval_digest")
        if self.revision.rights_digest!=self.rights.digest: raise ProjectLearningError("dataset rights binding mismatch")
    @property
    def digest(self): return digest_json({"rights_digest":self.rights.digest,"revision_digest":self.revision.digest,"outcome_digest":self.outcome_digest,"approval_digest":self.approval_digest})

def admit_project_outcome(outcome:ProjectOutcome,approval:LearningApproval,*,dataset_id:str,source_id:str)->ProjectTrainingAdmission:
    if not isinstance(outcome,ProjectOutcome) or not isinstance(approval,LearningApproval): raise ProjectLearningError("typed outcome and approval required")
    if outcome.status!="successful": raise ProjectLearningError("only successful outcomes may become training data")
    if not approval.approved: raise ProjectLearningError("explicit learning approval required")
    if approval.outcome_digest!=outcome.digest: raise ProjectLearningError("approval/outcome identity mismatch")
    rights=DatasetRights(dataset_id,source_id,"allowed",None,(approval.scope,),approval.rights_evidence_digest)
    # Content identity remains the approved project artifact, never raw crawler or memory payload.
    revision=DatasetRevision(dataset_id,0,outcome.content_digest,rights.digest,approval.transform_digest)
    return ProjectTrainingAdmission(rights,revision,outcome.digest,approval.digest)

__all__=["ProjectLearningError","ProjectOutcome","LearningApproval","ProjectTrainingAdmission","admit_project_outcome"]
