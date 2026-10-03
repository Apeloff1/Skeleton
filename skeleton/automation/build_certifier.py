"""Independent final certifier combining build and exact-head CI authority."""
from __future__ import annotations
from dataclasses import dataclass
from .build_acceptance import Acceptance
from .build_certificate import BuildCertificate
from .ci_evidence import CIEvidence
from .build_completion_proof import CompletionProof
from .repair_completion import require_repair_closure
@dataclass(frozen=True)
class CertificationInput:
 build_id:str;base_sha:str;final_sha:str;cycles:int;accepted:int;outcomes:tuple[str,...];canonical_drained:bool;integration_green:bool;receipts_verified:bool;journal_clear:bool
def certify(i:CertificationInput,ci:CIEvidence)->BuildCertificate:
 if ci.head_sha!=i.final_sha:raise ValueError("CI evidence is not for final build head")
 Acceptance(i.canonical_drained,i.integration_green,ci.green(),i.receipts_verified,i.journal_clear).require_complete()
 c=BuildCertificate(i.build_id,i.base_sha,i.final_sha,i.cycles,i.accepted,i.outcomes,"complete");c.validate();return c

def certify_with_proof(i:CertificationInput,ci:CIEvidence,*,canonical_fingerprint:str,build_state_sha256:str,receipt_sha256:tuple[str,...],repair_states:dict[str,str]|None=None)->tuple[BuildCertificate,CompletionProof]:
 require_repair_closure(repair_states or {})
 c=certify(i,ci)
 proof=CompletionProof(
  head_sha=i.final_sha,
  canonical_fingerprint=canonical_fingerprint,
  build_state_sha256=build_state_sha256,
  ci_evidence_sha256=ci.digest(),
  certificate_sha256=c.digest(),
  receipt_sha256=receipt_sha256,
 )
 proof.validate()
 return c,proof
