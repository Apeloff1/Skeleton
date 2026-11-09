from dataclasses import dataclass
import math
@dataclass(frozen=True)
class RiskFactor: name:str; value:float; weight:float
@dataclass(frozen=True)
class ChangeRisk:
 predicted:float; factors:tuple[RiskFactor,...]; hard_gates_passed:bool
 @property
 def admissible(self):return self.hard_gates_passed
@dataclass(frozen=True)
class RiskCalibration: predicted:float; observed_incident:bool
def _number(x):
 return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def estimate_risk(factors,*,hard_gates_passed):
 fs=tuple(factors)
 if not isinstance(hard_gates_passed,bool):raise TypeError("hard gate result must be bool")
 if any(not _number(f.value) or not _number(f.weight) or not 0<=f.value<=1 or f.weight<0 for f in fs):raise ValueError("invalid risk factor")
 total=sum(f.weight for f in fs);score=0 if not total else sum(f.value*f.weight for f in fs)/total
 return ChangeRisk(score,fs,hard_gates_passed)
def calibration_error(obs):
 o=tuple(obs)
 if any(not _number(x.predicted) or not 0<=x.predicted<=1 or not isinstance(x.observed_incident,bool) for x in o):raise ValueError("invalid calibration observation")
 return None if not o else sum(abs(x.predicted-float(x.observed_incident)) for x in o)/len(o)
