"""Uncertainty-aware task complexity estimates for VOL-312."""
from dataclasses import dataclass
@dataclass(frozen=True)
class ComplexityFeature:
 name:str; value:float; weight:float
 def __post_init__(self):
  if not self.name or self.value<0 or self.weight<0:raise ValueError("invalid complexity feature")
@dataclass(frozen=True)
class ComplexityEstimate:
 score:float; uncertainty:float; calibration_version:str; features:tuple[ComplexityFeature,...]; hard_limit:int
 def __post_init__(self):
  if self.score<0 or not 0<=self.uncertainty<=1 or not self.calibration_version or self.hard_limit<0:raise ValueError("invalid estimate")
 @property
 def admitted(self):return self.score<=self.hard_limit
@dataclass(frozen=True)
class EstimateRevision:
 previous:ComplexityEstimate; revised:ComplexityEstimate; reason:str
 def __post_init__(self):
  if not self.reason or self.reason.strip()!=self.reason:raise ValueError("revision reason required")
  if self.revised.hard_limit!=self.previous.hard_limit:raise ValueError("revision cannot move hard limit")
def estimate_complexity(features,*,calibration_version,hard_limit,uncertainty):
 fs=tuple(features)
 if not fs:return ComplexityEstimate(0,uncertainty,calibration_version,fs,hard_limit)
 score=sum(f.value*f.weight for f in fs)
 return ComplexityEstimate(score,uncertainty,calibration_version,fs,hard_limit)
def revise_estimate(previous,features,*,reason,uncertainty):
 revised=estimate_complexity(features,calibration_version=previous.calibration_version,hard_limit=previous.hard_limit,uncertainty=uncertainty)
 return EstimateRevision(previous,revised,reason)
