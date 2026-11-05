"""Monotonic nested deadlines and bounded retry budgets for native operations."""
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
import time
from ..contracts import fail

@dataclass(frozen=True,slots=True)
class TimedBudget:
    deadline_ns:int
    started_ns:int
    max_attempts:int
    operation:str

class Deadline:
    def __init__(self,*,duration_ns,clock=time.monotonic_ns):
        if type(duration_ns) is not int or not 1<=duration_ns<=600000000000:
            fail("invalid monotonic operation duration")
        if not callable(clock):fail("missing trusted monotonic time")
        self._clock=clock
        begin=clock()
        if type(begin) is not int or begin<0:fail("invalid monotonic timestamp")
        self._begin=begin
        self._deadline=begin+duration_ns

    def remaining_ns(self):
        now=self._clock()
        if type(now) is not int or now<self._begin:
            fail("nonmonotonic or invalid clock input")
        return max(0,self._deadline-now)

    def check(self):
        left=self.remaining_ns()
        if left<=0:fail("request monotonic deadline expired")
        return left

    def child(self,duration_ns):
        if type(duration_ns) is not int or not 1<=duration_ns<=600000000000:
            fail("invalid child time budget")
        left=self.check()
        return Deadline(duration_ns=min(left,duration_ns),clock=self._clock)

class RetryFence:
    def __init__(self,*,maximum=3,initial_ms=100,ceiling_ms=1000):
        if any(type(x) is not int for x in (maximum,initial_ms,ceiling_ms)):
            fail("retry policy requires exact integer values")
        if not 1<=maximum<=16 or not 1<=initial_ms<=ceiling_ms<=60000:
            fail("unbounded or invalid retry policy")
        self._lock=RLock()
        self._limit=maximum
        self._first=initial_ms
        self._cap=ceiling_ms
        self._used=0

    def next_delay_ms(self,*,failure_retryable,side_effect_known_absent):
        if failure_retryable is not True or side_effect_known_absent is not True:
            fail("unknown or already executed native side effect cannot retry")
        with self._lock:
            if self._used>=self._limit:fail("attempt budget exhausted")
            wait=min(self._cap,self._first*(2**self._used))
            self._used+=1
            return wait
