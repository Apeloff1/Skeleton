"""Temporal learning-control policy: decide what may enter durable weights."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class LearningTemporalPolicy:
 policy_id:str; subject:str; policy_year:int; minimum_stability_years:int; maximum_volatility_ppm:int
 require_invariance:bool=True; volatile_mode:str="retrieval-only"
 def __post_init__(self):
  if self.volatile_mode not in {"retrieval-only","quarantine"}: raise TemporalSignalError("invalid volatile learning mode")
  if self.minimum_stability_years<0: raise TemporalSignalError("invalid stability horizon")
  if not 0<=self.maximum_volatility_ppm<=1_000_000: raise TemporalSignalError("invalid volatility policy")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class TemporalLearningDecision:
 policy_digest:str; certificate_digest:str; content_digest:str; disposition:str; reason_codes:tuple[str,...]
 def __post_init__(self):
  if self.disposition not in {"weight-eligible","retrieval-only","quarantine"}: raise TemporalSignalError("invalid learning disposition")
  if tuple(sorted(set(self.reason_codes)))!=self.reason_codes: raise TemporalSignalError("learning reasons not canonical")
 @property
 def digest(self): return _digest(self.__dict__)

def decide_learning_disposition(*,policy,certificate,content_digest,stability_years,volatility_ppm,contradiction=False,counterfactual=False):
 _hex(content_digest,"content")
 if certificate.subject!=policy.subject or certificate.policy_year!=policy.policy_year: raise TemporalSignalError("learning temporal policy mismatch")
 reasons=[]
 if counterfactual: reasons.append("counterfactual-content")
 if contradiction: reasons.append("unresolved-contradiction")
 if stability_years<policy.minimum_stability_years: reasons.append("insufficient-stability")
 if volatility_ppm>policy.maximum_volatility_ppm: reasons.append("excess-volatility")
 if counterfactual or contradiction: disposition="quarantine"
 elif reasons: disposition=policy.volatile_mode
 else: disposition="weight-eligible"
 return TemporalLearningDecision(policy.digest,certificate.digest,content_digest,disposition,tuple(sorted(reasons)))

def require_weight_eligibility(decision):
 if decision.disposition!="weight-eligible": raise TemporalSignalError("content is not temporally eligible for durable weights")
 return decision.digest
__all__=["LearningTemporalPolicy","TemporalLearningDecision","decide_learning_disposition","require_weight_eligibility"]
