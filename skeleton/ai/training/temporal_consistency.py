"""Composite proof that temporal evidence is internally consistent."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
from .bitemporal_authority import require_no_future_knowledge
from .temporal_uncertainty import require_bounded_uncertainty
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalConsistencyProof:
 subject:str; policy_year:int; bitemporal_digest:str; provenance_digest:str; chronology_digest:str
 uncertainty_digest:str; decision_digest:str; consistent:bool
 def __post_init__(self):
  for n in ("bitemporal_digest","provenance_digest","chronology_digest","uncertainty_digest","decision_digest"): _hex(getattr(self,n),n)
  if not isinstance(self.subject,str) or not self.subject.strip(): raise TemporalSignalError("temporal consistency subject required")
  if isinstance(self.policy_year,bool) or not isinstance(self.policy_year,int) or not 1000<=self.policy_year<=9999: raise TemporalSignalError("invalid temporal consistency year")
  if self.consistent is not True: raise TemporalSignalError("temporal consistency proof must be affirmative")
 @property
 def digest(self): return _digest(self.__dict__)

def prove_temporal_consistency(*,subject,policy_year,bitemporal_snapshot,independence_receipt,chronology_receipt,uncertainty_receipt,decision):
 if bitemporal_snapshot.world_year!=policy_year: raise TemporalSignalError("bitemporal policy mismatch")
 require_no_future_knowledge(bitemporal_snapshot)
 require_bounded_uncertainty(uncertainty_receipt)
 if not chronology_receipt.acyclic: raise TemporalSignalError("chronology not acyclic")
 if independence_receipt.independent_root_count<2: raise TemporalSignalError("insufficient provenance independence")
 if decision.subject!=subject or decision.policy_year!=policy_year: raise TemporalSignalError("temporal decision mismatch")
 if decision.decision!="authorize": raise TemporalSignalError("temporal decision not authorized")
 return TemporalConsistencyProof(subject,policy_year,bitemporal_snapshot.digest,independence_receipt.digest,chronology_receipt.digest,uncertainty_receipt.digest,decision.digest,True)

__all__=["TemporalConsistencyProof","prove_temporal_consistency"]
