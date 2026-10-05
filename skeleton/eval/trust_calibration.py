"""Evidence-based trust calibration for VOL-328."""
from dataclasses import dataclass
@dataclass(frozen=True)
class CalibrationObservation:
 predicted:float; outcome:bool
 def __post_init__(self):
  if not 0<=self.predicted<=1:raise ValueError("confidence out of range")
@dataclass(frozen=True)
class TrustSignal:
 confidence:float; uncertainty:float; degraded:bool; evidence:tuple[str,...]
 def __post_init__(self):
  if not 0<=self.confidence<=1 or not 0<=self.uncertainty<=1:raise ValueError("invalid trust signal")
@dataclass(frozen=True)
class TrustPresentation:
 label:str; confidence:float; uncertainty:float; degraded:bool; calibration_error:float|None
def calibration_error(obs):
 o=tuple(obs)
 return None if not o else sum(abs(x.predicted-float(x.outcome)) for x in o)/len(o)
def present_trust(signal,observations=()):
 err=calibration_error(observations)
 label="degraded" if signal.degraded else ("uncertain" if signal.uncertainty>=.5 else "evidence-backed")
 return TrustPresentation(label,signal.confidence,signal.uncertainty,signal.degraded,err)
