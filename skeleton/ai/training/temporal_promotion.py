"""Bind qualified temporal evidence into candidate promotion admission."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError

def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalPromotionBinding:
 candidate_digest:str; promotion_digest:str; evidence_qualification_digest:str
 temporal_authority_digest:str; policy_year:int; exact_head_commit:str; qualified:bool
 def __post_init__(self):
  for n in ("candidate_digest","promotion_digest","evidence_qualification_digest","temporal_authority_digest"): _hex(getattr(self,n),n)
  if not isinstance(self.exact_head_commit,str) or len(self.exact_head_commit) not in (40,64) or any(c not in "0123456789abcdef" for c in self.exact_head_commit): raise TemporalSignalError("invalid temporal promotion exact head")
  if isinstance(self.policy_year,bool) or not isinstance(self.policy_year,int) or not 1000<=self.policy_year<=9999: raise TemporalSignalError("invalid temporal promotion year")
  if self.qualified is not True: raise TemporalSignalError("temporal promotion binding must be qualified")
 @property
 def digest(self): return _digest(self.__dict__)

def bind_temporal_promotion(candidate,promotion,qualification,authority,*,policy_year):
 if promotion.candidate_digest!=candidate.digest: raise TemporalSignalError("temporal promotion candidate mismatch")
 if not promotion.qualified: raise TemporalSignalError("base promotion evidence not qualified")
 if not qualification.qualified or qualification.temporal_authority_digest!=authority.digest: raise TemporalSignalError("temporal evidence authority mismatch")
 if authority.policy_year!=policy_year or authority.authorized is not True: raise TemporalSignalError("temporal promotion policy year or authority mismatch")
 return TemporalPromotionBinding(candidate.digest,promotion.digest,qualification.digest,authority.digest,policy_year,promotion.exact_head_commit,True)

def require_temporal_promotion(binding,*,candidate_digest,promotion_digest,exact_head_commit):
 if binding.candidate_digest!=candidate_digest or binding.promotion_digest!=promotion_digest: raise TemporalSignalError("temporal promotion identity mismatch")
 if binding.exact_head_commit!=exact_head_commit: raise TemporalSignalError("temporal promotion exact-head mismatch")
 if not binding.qualified: raise TemporalSignalError("temporal promotion not qualified")
 return binding.digest

__all__=["TemporalPromotionBinding","bind_temporal_promotion","require_temporal_promotion"]
