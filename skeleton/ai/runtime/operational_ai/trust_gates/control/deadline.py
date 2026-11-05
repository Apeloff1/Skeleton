"""Monotonic deadline minimization and bounded retry planning."""
from __future__ import annotations
import time
from ..contracts import fail

class Deadline:
    def __init__(self,deadline_ns,*,clock=time.monotonic_ns):
        if not callable(clock): fail("deadline clock unavailable")
        now=clock()
        if type(now) is not int or type(deadline_ns) is not int:
            fail("deadline requires integer nanoseconds")
        if not now<deadline_ns<=now+3600*1000000000:
            fail("deadline expired or excessive")
        self._clock=clock
        self._end=deadline_ns

    @property
    def end_ns(self): return self._end

    def remaining_ns(self):
        return max(0,self._end-self._clock())

    def require_live(self):
        if self.remaining_ns()==0: fail("deadline exhausted")
        return self.remaining_ns()

    def child(self,operator_duration_ns):
        if type(operator_duration_ns) is not int or not 1<=operator_duration_ns<=3600*1000000000:
            fail("invalid child budget")
        now=self._clock()
        if now>=self._end: fail("cannot extend expired deadline")
        return Deadline(min(self._end,now+operator_duration_ns),clock=self._clock)

class RetryBudget:
    def __init__(self,*,attempts=3,base_ms=100,ceiling_ms=1000):
        if any(type(x) is not int for x in (attempts,base_ms,ceiling_ms)):
            fail("integer retries required")
        if not 1<=attempts<=16 or not 1<=base_ms<=ceiling_ms<=60000:
            fail("unbounded retry policy")
        self._maximum=attempts;self._base=base_ms;self._cap=ceiling_ms
        self._count=0

    def next_delay_ms(self,*,retryable,side_effect_committed=False):
        if type(retryable) is not bool or type(side_effect_committed) is not bool:
            fail("retry classification required")
        if not retryable or side_effect_committed:
            fail("nonretryable failure or committed side effect")
        if self._count>=self._maximum: fail("retry budget exhausted")
        delay=min(self._cap,self._base*(2**self._count))
        self._count+=1
        return delay
