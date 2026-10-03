"""Service-level objectives detect degraded autonomous build operation."""
from __future__ import annotations
from dataclasses import dataclass
from .build_telemetry import BuildTelemetry
@dataclass(frozen=True)
class SLOResult:
 healthy:bool;violations:tuple[str,...]
def evaluate(t:BuildTelemetry)->SLOResult:
 t.validate();v=[]
 if t.cycles>=5 and t.acceptance_rate<0.15:v.append("acceptance_rate")
 if t.quarantined>3:v.append("quarantine_pressure")
 if t.cycles and t.validation_seconds/t.cycles>900:v.append("validation_latency")
 return SLOResult(not v,tuple(v))
