"""Monotonic deadlines and aggregate time budgets for shell operations."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class Deadline:
    expires_at:float

    def __post_init__(self)->None:
        if self.expires_at<0:raise ValueError("deadline may not be negative")

    def remaining(self,now:float)->float:
        return max(0.0,self.expires_at-now)

    def expired(self,now:float)->bool:
        return now>=self.expires_at


class DeadlineExceeded(TimeoutError):pass


class DeadlineClock:
    def __init__(self,*,clock:Callable[[],float]=time.monotonic)->None:self._clock=clock

    def after(self,seconds:float)->Deadline:
        if seconds<=0:raise ValueError("deadline duration must be positive")
        return Deadline(self._clock()+seconds)

    def remaining(self,deadline:Deadline)->float:return deadline.remaining(self._clock())

    def require(self,deadline:Deadline)->float:
        remaining=self.remaining(deadline)
        if remaining<=0:raise DeadlineExceeded("shell operation deadline exceeded")
        return remaining

    def clamp_timeout(self,deadline:Deadline,requested:float)->float:
        if requested<=0:raise ValueError("requested timeout must be positive")
        return min(requested,self.require(deadline))


@dataclass(frozen=True)
class TimeBudgetSnapshot:
    total_seconds:float
    consumed_seconds:float
    started_at:float

    @property
    def remaining_seconds(self)->float:
        return max(0.0,self.total_seconds-self.consumed_seconds)

    @property
    def exhausted(self)->bool:return self.remaining_seconds<=0


class TimeBudget:
    """Explicit aggregate runtime budget recorded by callers."""

    def __init__(
        self,
        total_seconds:float,
        *,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        if total_seconds<=0:raise ValueError("total_seconds must be positive")
        self.total_seconds=float(total_seconds)
        self._clock=clock
        self._started=clock()
        self._consumed=0.0
        self._lock=threading.RLock()

    def reserve(self,requested_seconds:float)->float:
        if requested_seconds<=0:raise ValueError("requested_seconds must be positive")
        with self._lock:
            remaining=self.total_seconds-self._consumed
            if remaining<=0:raise DeadlineExceeded("time budget exhausted")
            return min(requested_seconds,remaining)

    def record(self,duration_seconds:float)->TimeBudgetSnapshot:
        if duration_seconds<0:raise ValueError("duration_seconds may not be negative")
        with self._lock:
            self._consumed+=duration_seconds
            return self.snapshot()

    def snapshot(self)->TimeBudgetSnapshot:
        with self._lock:
            return TimeBudgetSnapshot(self.total_seconds,self._consumed,self._started)

    def require(self)->float:
        snap=self.snapshot()
        if snap.exhausted:raise DeadlineExceeded("time budget exhausted")
        return snap.remaining_seconds
