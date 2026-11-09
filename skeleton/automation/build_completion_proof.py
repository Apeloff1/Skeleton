"""Composite proof object for machine-verifiable autonomous completion."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class CompletionProof:
 head_sha:str;canonical_fingerprint:str;build_state_sha256:str;ci_evidence_sha256:str;certificate_sha256:str;receipt_sha256:tuple[str,...]
 def validate(self):
  if len(self.head_sha)!=40:raise ValueError("completion proof head malformed")
  for v in (self.canonical_fingerprint,self.build_state_sha256,self.ci_evidence_sha256,self.certificate_sha256,*self.receipt_sha256):
   if len(v)!=64 or any(c not in "0123456789abcdef" for c in v):raise ValueError("completion proof digest malformed")
 def digest(self):
  self.validate();return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(",",":")).encode()).hexdigest()
