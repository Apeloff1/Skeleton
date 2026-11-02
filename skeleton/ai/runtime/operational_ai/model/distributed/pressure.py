"""Conservative CPU/RAM pressure classification with unknown telemetry blocked."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from .workers import WorkerError

@dataclass(frozen=True,slots=True)
class Pressure:
    cpu_fraction:float|None
    memory_fraction:float|None
    queue_depth:int|None
    unknown:bool=False

@dataclass(frozen=True,slots=True)
class PressureDecision:
    mode:str
    max_new_admissions:int
    reasons:tuple[str,...]


def assess_pressure(p:Pressure,*,soft:float=.75,hard:float=.92)->PressureDecision:
    if not 0<soft<hard<=1:raise WorkerError('invalid pressure limits')
    reasons=[]
    if p.unknown or p.cpu_fraction is None or p.memory_fraction is None or p.queue_depth is None:
        return PressureDecision('blocked',0,('telemetry-unknown',))
    if (any(not isinstance(x,(float,int)) or not isfinite(x) or not 0<=x<=1
            for x in (p.cpu_fraction,p.memory_fraction)) or type(p.queue_depth) is not int or p.queue_depth<0):
        raise WorkerError('malformed pressure data')
    peak=max(p.cpu_fraction,p.memory_fraction)
    if peak>=hard or p.queue_depth>1000:
        return PressureDecision('blocked',0,('hard-resource-pressure',))
    if peak>=soft or p.queue_depth>200:
        return PressureDecision('reduced',1,('soft-resource-pressure',))
    return PressureDecision('normal',8,())
