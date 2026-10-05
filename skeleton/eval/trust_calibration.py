"""Evidence-based trust calibration for VOL-328."""
from dataclasses import dataclass
import math
@dataclass(frozen=True)
class CalibrationObservation:
 predicted:float; outcome:bool
 def __post_init__(self):
  if isinstance(self.predicted,bool) or not isinstance(self.predicted,(int,float)) or not math.isfinite(self.predicted) or not 0<=self.predicted<=1 or not isinstance(self.outcome,bool):raise ValueError("confidence out of range")
@dataclass(frozen=True)
class TrustSignal:
 confidence:float; uncertainty:float; degraded:bool; evidence:tuple[str,...]
 def __post_init__(self):
  if not isinstance(self.degraded,bool) or any(not isinstance(e,str) or not e.strip() for e in self.evidence) or len(self.evidence)!=len(set(self.evidence)) or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in (self.confidence,self.uncertainty)) or not 0<=self.confidence<=1 or not 0<=self.uncertainty<=1:raise ValueError("invalid trust signal")
@dataclass(frozen=True)
class TrustPresentation:
 label:str; confidence:float; uncertainty:float; degraded:bool; calibration_error:float|None
def calibration_error(obs):
 o=tuple(obs)
 return None if not o else sum(abs(x.predicted-float(x.outcome)) for x in o)/len(o)
def present_trust(signal,observations=()):
 err=calibration_error(observations)
 label="degraded" if signal.degraded else ("uncertain" if signal.uncertainty>=.5 or not signal.evidence else "evidence-backed")
 return TrustPresentation(label,signal.confidence,signal.uncertainty,signal.degraded,err)
