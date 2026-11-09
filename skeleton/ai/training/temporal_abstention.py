"""Fail-closed abstention policy for unresolved temporal evidence."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError

def _ppm(v,n):
 if isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=1_000_000: raise TemporalSignalError(f"invalid {n}")
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()

@dataclass(frozen=True)
class TemporalDecision:
 subject:str; policy_year:int; authority_digest:str; decision:str; reason_codes:tuple[str,...]
 def __post_init__(self):
  if not isinstance(self.subject,str) or not self.subject.strip(): raise TemporalSignalError("temporal decision subject required")
  if isinstance(self.policy_year,bool) or not isinstance(self.policy_year,int) or not 1000<=self.policy_year<=9999: raise TemporalSignalError("invalid temporal policy year")
  if not isinstance(self.authority_digest,str) or len(self.authority_digest)!=64 or any(ch not in "0123456789abcdef" for ch in self.authority_digest): raise TemporalSignalError("invalid decision authority digest")
  if self.decision not in {"authorize","abstain","reject"}: raise TemporalSignalError("invalid temporal decision")
  if tuple(sorted(set(self.reason_codes)))!=self.reason_codes: raise TemporalSignalError("reason codes must be canonical")
 @property
 def digest(self): return _digest(self.__dict__)

def decide_temporal_authority(*,subject,policy_year,authority_digest,support_ppm,opposition_ppm,uncertainty_ppm,regime_change_ppm,provenance_roots,minimum_roots=2):
 for n in ("support","opposition","uncertainty","regime change"):
  _ppm({"support":support_ppm,"opposition":opposition_ppm,"uncertainty":uncertainty_ppm,"regime change":regime_change_ppm}[n],n)
 if isinstance(provenance_roots,bool) or not isinstance(provenance_roots,int) or provenance_roots<0: raise TemporalSignalError("invalid provenance roots")
 if isinstance(minimum_roots,bool) or not isinstance(minimum_roots,int) or minimum_roots<2: raise TemporalSignalError("invalid minimum provenance roots")
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
