"""Research-backed composition gate for temporal learning authority."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
from .temporal_drift import require_calibrated_forecaster

def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalResearchAuthority:
 subject:str; policy_year:int; temporal_authority_digest:str; calibration_digest:str
 change_point_digest:str; historical_snapshot_digest:str; research_basis_digests:tuple[str,...]
 authorized:bool
 def __post_init__(self):
  for n in ("temporal_authority_digest","calibration_digest","change_point_digest","historical_snapshot_digest"): _hex(getattr(self,n),n)
  if len(self.research_basis_digests)<3: raise TemporalSignalError("multiple independent research bases required")
  for d in self.research_basis_digests: _hex(d,"research basis")
  if len(set(self.research_basis_digests))!=len(self.research_basis_digests): raise TemporalSignalError("duplicate research basis")
  if self.authorized is not True: raise TemporalSignalError("temporal research authority must be affirmative")
 @property
 def digest(self): return _digest(self.__dict__)

def authorize_research_temporal_plane(*,subject,policy_year,temporal_receipt,calibration_receipt,change_point_state,historical_snapshot,research_basis_digests):
 if temporal_receipt.subject!=subject or change_point_state.subject!=subject: raise TemporalSignalError("research authority subject mismatch")
 if temporal_receipt.policy_year!=policy_year or change_point_state.policy_year!=policy_year or historical_snapshot.as_of_year!=policy_year: raise TemporalSignalError("research authority time mismatch")
 require_calibrated_forecaster(calibration_receipt)
 if change_point_state.change_probability_ppm>=700_000: raise TemporalSignalError("unresolved high-probability regime change")
 return TemporalResearchAuthority(subject,policy_year,temporal_receipt.digest,calibration_receipt.digest,change_point_state.digest,historical_snapshot.digest,tuple(sorted(research_basis_digests)),True)

__all__=["TemporalResearchAuthority","authorize_research_temporal_plane"]
