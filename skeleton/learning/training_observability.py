"""Training telemetry that detects divergence without retaining raw restricted data."""
from dataclasses import dataclass
import math
class TrainingObservabilityError(ValueError): pass
@dataclass(frozen=True, slots=True)
class TrainingMetric: run_id:str; step:int; name:str; value:float
@dataclass(frozen=True, slots=True)
class TrainingAlert: run_id:str; step:int; code:str; severity:str
class TrainingTelemetry:
    def __init__(self,*,minimum_throughput:float=0.0): self.minimum_throughput=minimum_throughput; self._metrics=[]; self._alerts=[]
    def record(self,metric:TrainingMetric)->tuple[TrainingAlert,...]:
        if not metric.run_id or metric.step<0 or not metric.name: raise TrainingObservabilityError("invalid metric identity")
        alerts=[]
        if not math.isfinite(metric.value): alerts.append(TrainingAlert(metric.run_id,metric.step,"non_finite_value","critical"))
        elif metric.name=="throughput" and metric.value<self.minimum_throughput: alerts.append(TrainingAlert(metric.run_id,metric.step,"throughput_collapse","warning"))
        self._metrics.append(metric); self._alerts.extend(alerts); return tuple(alerts)
    def stall(self,*,run_id:str,last_step:int,current_step:int)->TrainingAlert|None:
        if current_step<last_step: raise TrainingObservabilityError("step regression")
        if current_step==last_step:
            alert=TrainingAlert(run_id,current_step,"training_stall","warning"); self._alerts.append(alert); return alert
        return None
    @property
    def alerts(self): return tuple(self._alerts)
