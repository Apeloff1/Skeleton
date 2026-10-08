"""Epoch-bound revocation for temporal certificates and training admissions."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalRevocation:
 target_digest:str; target_kind:str; epoch:int; reason_code:str; authority_id:str; evidence_digest:str
 def __post_init__(self):
  _hex(self.target_digest,"revocation target"); _hex(self.evidence_digest,"revocation evidence")
  if self.target_kind not in {"certificate","training-admission","promotion-binding"}: raise TemporalSignalError("invalid revocation target")
  if self.reason_code not in {"evidence-invalidated","regime-change","provenance-compromised","benchmark-regression","operator-revocation"}: raise TemporalSignalError("invalid revocation reason")
  if isinstance(self.epoch,bool) or not isinstance(self.epoch,int) or self.epoch<0 or not isinstance(self.authority_id,str) or not self.authority_id.strip(): raise TemporalSignalError("invalid revocation authority")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class RevocationRegistry:
 revocations:tuple[TemporalRevocation,...]=()
 def revoke(self,item):
  if any(x.target_digest==item.target_digest and x.epoch>=item.epoch for x in self.revocations): raise TemporalSignalError("stale or duplicate revocation")
  return RevocationRegistry(self.revocations+(item,))
 def require_not_revoked(self,target_digest,*,epoch):
  matches=[x for x in self.revocations if x.target_digest==target_digest and x.epoch<=epoch]
  if matches: raise TemporalSignalError("temporal authority revoked")
  return True
 @property
 def digest(self): return _digest(tuple(x.digest for x in self.revocations))

__all__=["TemporalRevocation","RevocationRegistry"]
