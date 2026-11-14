"""Fail-closed admission checks before durable mutation and native dispatch."""
from __future__ import annotations
from dataclasses import dataclass
import math
from .canonical import require_int
from .errors import deny
from .spec import JobSpec,WorkLimits


@dataclass(frozen=True, slots=True)
class Telemetry:
    memory_pressure: float
    cpu_pressure: float
    queue_pressure: float
    observed_ms: int

    def __post_init__(self):
        for name in ("memory_pressure","cpu_pressure","queue_pressure"):
            value=getattr(self,name)
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1:
                deny("admission-telemetry")
        require_int(self.observed_ms,0,2**63-1,"telemetry-time")


class AdmissionPolicy:
    def __init__(self,*,maximum_pressure:float=0.9,maximum_sample_age_ms:int=2000):
        if type(maximum_pressure) is not float or not 0<maximum_pressure<=1:
            deny("admission-threshold")
        self.maximum_pressure=maximum_pressure
        self.maximum_sample_age_ms=require_int(maximum_sample_age_ms,1,60000,"sample-age")

    def check(self,spec:JobSpec,limits:WorkLimits,telemetry:Telemetry,*,now_ms:int)->str:
        if type(spec) is not JobSpec or type(limits) is not WorkLimits:
            deny("admission-contract")
        require_int(now_ms,0,2**63-1,"clock")
        if type(telemetry) is not Telemetry:
            deny("admission-no-telemetry")
        if telemetry.observed_ms>now_ms or now_ms-telemetry.observed_ms>self.maximum_sample_age_ms:
            deny("admission-stale")
        if max(telemetry.memory_pressure,telemetry.cpu_pressure,
               telemetry.queue_pressure)>=self.maximum_pressure:
            deny("admission-overloaded")
        if len(spec.question.encode("utf-8"))>limits.input_bytes:
            deny("admission-input-bytes")
        if spec.expires_ms-spec.created_ms>limits.deadline_ms:
            deny("admission-deadline")
        return "admitted"
