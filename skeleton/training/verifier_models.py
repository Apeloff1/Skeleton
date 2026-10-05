"""Independent verifier model calibration contracts for VOL-152."""
from __future__ import annotations
from dataclasses import dataclass
import math,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class VerifierError(ValueError): pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v): raise VerifierError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class VerifierModel:
 verifier_id:str;model_digest:str;training_family_id:str
 def __post_init__(self):
  object.__setattr__(self,"verifier_id",_id(self.verifier_id,"verifier_id"));object.__setattr__(self,"training_family_id",_id(self.training_family_id,"training_family_id"))
  if not _SHA.fullmatch(self.model_digest): raise VerifierError("model digest required")
@dataclass(frozen=True,slots=True)
class VerificationScore:
 verifier_id:str;generator_id:str;confidence:float;accepted:bool
 def __post_init__(self):
  object.__setattr__(self,"verifier_id",_id(self.verifier_id,"verifier_id"));object.__setattr__(self,"generator_id",_id(self.generator_id,"generator_id"))
  if self.verifier_id==self.generator_id: raise VerifierError("verifier authority must be independent")
  if not math.isfinite(self.confidence) or not 0<=self.confidence<=1: raise VerifierError("invalid confidence")
@dataclass(frozen=True,slots=True)
class VerifierCalibration:
 verifier_id:str;false_accept_rate:float;false_reject_rate:float;sample_count:int
 def __post_init__(self):
  object.__setattr__(self,"verifier_id",_id(self.verifier_id,"verifier_id"))
  if self.sample_count<1 or any(not math.isfinite(x) or not 0<=x<=1 for x in (self.false_accept_rate,self.false_reject_rate)): raise VerifierError("invalid calibration")
def ensemble_eligible(models,calibrations,max_false_accept):
 by={c.verifier_id:c for c in calibrations}
 if any(m.verifier_id not in by or by[m.verifier_id].false_accept_rate>max_false_accept for m in models): return False
 if len({m.training_family_id for m in models})<2: return False
 return len(models)>=2