"""Provenance-bound diagnostic project metrics for VOL-117."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class MetricError(ValueError):pass
class MetricClass(str,Enum): ACTIVITY="activity"; THROUGHPUT="throughput"; QUALITY="quality"; RISK="risk"; OUTCOME="outcome"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise MetricError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise MetricError(f"{f} must be sha256")
 return v
@dataclass(frozen=True,slots=True)
class MetricDefinition:
 metric_id:str;metric_class:MetricClass;unit:str;source_kind:str;completion_authority:bool=False
 def __post_init__(self):
  object.__setattr__(self,"metric_id",_id(self.metric_id,"metric_id"))
  if not self.unit.strip() or not self.source_kind.strip():raise MetricError("metric unit and source required")
  if self.completion_authority:raise MetricError("diagnostic metric cannot be completion authority")
@dataclass(frozen=True,slots=True)
class MetricObservation:
 metric_id:str;value:float;numerator:int;denominator:int;source_digest:str;observed_tick:int
 def __post_init__(self):
  object.__setattr__(self,"metric_id",_id(self.metric_id,"metric_id"));_sha(self.source_digest,"source_digest")
  if self.denominator<1 or self.numerator<0 or self.observed_tick<0:raise MetricError("metric provenance bounds invalid")
  json.dumps(self.value,allow_nan=False)
@dataclass(frozen=True,slots=True)
class ProjectMetric:
 definition:MetricDefinition;observation:MetricObservation
 def __post_init__(self):
  if self.definition.metric_id!=self.observation.metric_id:raise MetricError("definition/observation mismatch")
class MetricRegistry:
 def __init__(self,definitions):self.definitions={d.metric_id:d for d in definitions}
 def observe(self,observation):
  d=self.definitions.get(observation.metric_id)
  if d is None:raise MetricError("unknown metric")
  return ProjectMetric(d,observation)
 def stale(self,metric,current_tick,max_age):return current_tick-metric.observation.observed_tick>max_age
