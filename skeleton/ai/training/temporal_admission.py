"""Transactional boundary between temporal learning authority and candidate training."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalTrainingAdmission:
 admission_id:str; content_digest:str; learning_decision_digest:str; certificate_digest:str
 certificate_registration_digest:str; exact_head_commit:str; base_model_digest:str; dataset_digest:str
 authority_id:str; epoch:int
 def __post_init__(self):
  for n in ("content_digest","learning_decision_digest","certificate_digest","certificate_registration_digest","base_model_digest","dataset_digest"): _hex(getattr(self,n),n)
  if not isinstance(self.admission_id,str) or not self.admission_id.strip() or not isinstance(self.authority_id,str) or not self.authority_id.strip(): raise TemporalSignalError("training admission identity required")
  if not isinstance(self.exact_head_commit,str) or len(self.exact_head_commit) not in (40,64) or any(ch not in "0123456789abcdef" for ch in self.exact_head_commit): raise TemporalSignalError("invalid admission exact head")
  if isinstance(self.epoch,bool) or not isinstance(self.epoch,int) or self.epoch<0: raise TemporalSignalError("invalid training admission epoch")
 @property
 def digest(self): return _digest(self.__dict__)

def admit_temporal_training(*,admission_id,content_digest,decision,certificate,registry,exact_head_commit,base_model_digest,dataset_digest,authority_id,epoch):
 if decision.disposition!="weight-eligible": raise TemporalSignalError("temporal content is not weight eligible")
 if decision.content_digest!=content_digest: raise TemporalSignalError("temporal learning content identity mismatch")
 if certificate.authorized is not True: raise TemporalSignalError("temporal certificate not authorized")
 if decision.certificate_digest!=certificate.digest: raise TemporalSignalError("learning decision certificate mismatch")
 registry.require_active(certificate.digest,policy_year=certificate.policy_year)
 if certificate.exact_head_commit!=exact_head_commit: raise TemporalSignalError("certificate exact-head mismatch")
 return TemporalTrainingAdmission(admission_id,content_digest,decision.digest,certificate.digest,registry.require_active(certificate.digest,policy_year=certificate.policy_year),exact_head_commit,base_model_digest,dataset_digest,authority_id,epoch)

__all__=["TemporalTrainingAdmission","admit_temporal_training"]
