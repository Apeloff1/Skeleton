"""Fail-closed abstention policy for unresolved temporal evidence."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()

@dataclass(frozen=True)
class TemporalDecision:
 subject:str; policy_year:int; authority_digest:str; decision:str; reason_codes:tuple[str,...]
 def __post_init__(self):
  if self.decision not in {"authorize","abstain","reject"}: raise TemporalSignalError("invalid temporal decision")
  if tuple(sorted(set(self.reason_codes)))!=self.reason_codes: raise TemporalSignalError("reason codes must be canonical")
 @property
 def digest(self): return _digest(self.__dict__)

def decide_temporal_authority(*,subject,policy_year,authority_digest,support_ppm,opposition_ppm,uncertainty_ppm,regime_change_ppm,provenance_roots,minimum_roots=2):
 reasons=[]
 if provenance_roots<minimum_roots: reasons.append("insufficient-independent-provenance")
 if uncertainty_ppm>250000: reasons.append("high-uncertainty")
 if regime_change_ppm>=700000: reasons.append("unresolved-regime-change")
 if opposition_ppm>100000: reasons.append("material-opposition")
 if support_ppm<700000: reasons.append("insufficient-support")
 severe={"insufficient-independent-provenance","unresolved-regime-change","material-opposition"}
 decision="reject" if severe.intersection(reasons) else "abstain" if reasons else "authorize"
 return TemporalDecision(subject,policy_year,authority_digest,decision,tuple(sorted(reasons)))

def require_temporal_authorization(decision):
 if decision.decision!="authorize": raise TemporalSignalError("temporal authority did not authorize")
 return decision.digest
__all__=["TemporalDecision","decide_temporal_authority","require_temporal_authorization"]
