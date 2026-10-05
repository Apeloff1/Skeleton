"""Privacy-bounded training observability for VOL-147."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import math,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class ObservabilityError(ValueError):pass
class AlertKind(str,Enum): NON_FINITE="non_finite"; STALL="stall"; THROUGHPUT="throughput_collapse"; RESOURCE="resource_anomaly"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise ObservabilityError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class TrainingMetric:
 run_id:str;metric_id:str;value:float;tick:int
 def __post_init__(self):
  object.__setattr__(self,"run_id",_id(self.run_id,"run_id"));object.__setattr__(self,"metric_id",_id(self.metric_id,"metric_id"))
  if self.tick<0:raise ObservabilityError("tick must be nonnegative")
@dataclass(frozen=True,slots=True)
class TrainingTrace:
 run_id:str;state_digest:str;last_progress_tick:int
 def __post_init__(self):
  object.__setattr__(self,"run_id",_id(self.run_id,"run_id"))
  if not _SHA.fullmatch(self.state_digest):raise ObservabilityError("trace carries digest only")
  if self.last_progress_tick<0:raise ObservabilityError("progress tick invalid")
@dataclass(frozen=True,slots=True)
class TrainingAlert:
 run_id:str;kind:AlertKind;metric_id:str;tick:int
class TrainingMonitor:
 def evaluate(self,metric,trace,current_tick,stall_ticks,min_throughput,max_resource):
  if metric.run_id!=trace.run_id:raise ObservabilityError("run mismatch")
  alerts=[]
  if not math.isfinite(metric.value):alerts.append(AlertKind.NON_FINITE)
  if current_tick-trace.last_progress_tick>=stall_ticks:alerts.append(AlertKind.STALL)
  if metric.metric_id=="METRIC.THROUGHPUT" and math.isfinite(metric.value) and metric.value<min_throughput:alerts.append(AlertKind.THROUGHPUT)
  if metric.metric_id=="METRIC.RESOURCE" and math.isfinite(metric.value) and metric.value>max_resource:alerts.append(AlertKind.RESOURCE)
  return tuple(TrainingAlert(metric.run_id,k,metric.metric_id,current_tick) for k in alerts)
