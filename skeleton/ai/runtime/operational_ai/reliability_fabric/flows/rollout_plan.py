"""Externally verified exact-head gate evidence before operator model rollout."""
from __future__ import annotations
from dataclasses import dataclass
from ..contracts import fail
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import identity_hash
from skeleton.ai.runtime.operational_ai.trust_gates.applications.release_evidence import (
    REQUIRED,qualify_record)

@dataclass(frozen=True,slots=True)
class RolloutReceipt:
    head_sha256:str
    model_sha256:str
    token_sha256:str
    evidence_sha256:str
    applied:bool=False
    release_certified:bool=False

def prepare(*,head_sha256,model_sha256,token_sha256,check_statuses,
            reviewer_approved,native_e2e,rights_approved,installation_qualified,
            source_of_statuses):
    for x in (head_sha256,model_sha256,token_sha256):identity_hash(x)
    if source_of_statuses!="actual-final-head-github-api":
        fail("workflow statuses must be externally observed at final head")
    result=qualify_record(head_sha=head_sha256,observed=check_statuses,
          reviewed=reviewer_approved,native_e2e=native_e2e,
          rights_approved=rights_approved,
          installation_proved=installation_qualified)
    return RolloutReceipt(head_sha256,model_sha256,token_sha256,
                          result["input_sha256"])
