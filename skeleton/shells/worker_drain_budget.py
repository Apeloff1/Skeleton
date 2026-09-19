"""Aggregate budget for bounded worker drain passes."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class DrainLimits:
    max_items:int=100
    max_failures:int=10
    max_seconds:float=30.0

    def __post_init__(self)->None:
        if self.max_items<=0 or self.max_failures<0 or self.max_seconds<=0:
            raise ValueError("invalid drain limits")


@dataclass(frozen=True)
class DrainUsage:
    items:int=0
    failures:int=0
    started_at:float=0.0

    def to_dict(self)->dict[str,int|float]:
        return {"items":self.items,"failures":self.failures,"started_at":self.started_at}


class WorkerDrainBudget:
    def __init__(
        self,
        limits:DrainLimits|None=None,
        *,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        self.limits=limits or DrainLimits()
        self._clock=clock
        self._usage=DrainUsage(started_at=clock())
        self._lock=threading.RLock()

    def remaining_seconds(self)->float:
        with self._lock:
            return max(0.0,self.limits.max_seconds-(self._clock()-self._usage.started_at))

    def can_start(self)->bool:
        with self._lock:
            return (
                self._usage.items<self.limits.max_items
                and self._usage.failures<=self.limits.max_failures
                and self.remaining_seconds()>0
            )

    def record(self,*,ok:bool)->DrainUsage:
        with self._lock:
            if not self.can_start():raise RuntimeError("worker drain budget exhausted")
            self._usage=DrainUsage(
                items=self._usage.items+1,
                failures=self._usage.failures+(0 if ok else 1),
                started_at=self._usage.started_at,
            )
            return self._usage

    def exhausted_reasons(self)->tuple[str,...]:
        with self._lock:
            reasons=[]
            if self._usage.items>=self.limits.max_items:reasons.append("items")
            if self._usage.failures>self.limits.max_failures:reasons.append("failures")
            if self.remaining_seconds()<=0:reasons.append("time")
            return tuple(reasons)

    def snapshot(self)->DrainUsage:
        with self._lock:return self._usage
