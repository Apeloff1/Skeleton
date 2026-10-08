"""Single proof-carrying temporal decision certificate for promotion boundaries."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalDecisionCertificate:
 subject:str; policy_year:int; exact_head_commit:str; authority_digest:str; benchmark_digest:str
 provenance_digest:str; uncertainty_digest:str; drift_digest:str; causality_digest:str
 invariance_digest:str; historical_snapshot_digest:str; decision_digest:str; authorized:bool
 def __post_init__(self):
  for n in ("exact_head_commit","authority_digest","benchmark_digest","provenance_digest","uncertainty_digest","drift_digest","causality_digest","invariance_digest","historical_snapshot_digest","decision_digest"): _hex(getattr(self,n),n)
  if self.authorized is not True: raise TemporalSignalError("certificate must be affirmative")
 @property
 def digest(self): return _digest(self.__dict__)

def issue_temporal_certificate(*,subject,policy_year,exact_head_commit,authority,benchmark,provenance,uncertainty,drift,causality,invariance,historical_snapshot,decision):
 if getattr(authority,"subject",None)!=subject: raise TemporalSignalError("authority subject mismatch")
 if getattr(authority,"policy_year",None)!=policy_year: raise TemporalSignalError("authority policy year mismatch")
 if benchmark.exact_head_commit!=exact_head_commit or not benchmark.passed: raise TemporalSignalError("temporal benchmark not valid for exact head")
 if provenance.independent_root_count<2: raise TemporalSignalError("provenance independence insufficient")
 if uncertainty.sample_count<20 or uncertainty.radius_ppm>250_000: raise TemporalSignalError("temporal uncertainty unacceptable")
 if drift.high_drift or drift.disagreement: raise TemporalSignalError("temporal regime unstable")
 if not causality.acyclic: raise TemporalSignalError("causal chronology invalid")
 if not invariance.invariant: raise TemporalSignalError("cross-regime invariance absent")
 if decision.decision!="authorize": raise TemporalSignalError("temporal decision not authorized")
 return TemporalDecisionCertificate(subject,policy_year,exact_head_commit,authority.digest,benchmark.digest,provenance.digest,uncertainty.digest,drift.digest,causality.digest,invariance.digest,historical_snapshot.digest,decision.digest,True)

__all__=["TemporalDecisionCertificate","issue_temporal_certificate"]
