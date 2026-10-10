from dataclasses import dataclass
import math
@dataclass(frozen=True)
class FreshnessSLI:
 age_seconds:float; objective_seconds:float
 def __post_init__(self):
  if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in (self.age_seconds,self.objective_seconds)):raise ValueError("valid freshness SLI required")
@dataclass(frozen=True)
class DataSLO:
 availability_target:float; freshness_target:float; correctness_target:float
 def __post_init__(self):
  if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1 for x in (self.availability_target,self.freshness_target,self.correctness_target)):raise ValueError("SLO targets must be probabilities")
@dataclass(frozen=True)
class DataServiceHealth: available:bool; fresh:bool; correct:bool
def health(*,available,freshness,correct):
 if not isinstance(available,bool) or not isinstance(correct,bool):raise TypeError("health signals must be boolean")
 return DataServiceHealth(available,freshness.age_seconds<=freshness.objective_seconds,correct)
