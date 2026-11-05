"""Fail-closed native model circuit with explicit human-authorized reset."""
from __future__ import annotations
from threading import RLock
from ..contracts import fail

class Circuit:
    def __init__(self,*,failure_ceiling=4):
        if type(failure_ceiling) is not int or not 1<=failure_ceiling<=128:
            fail("invalid failure circuit threshold")
        self._lock=RLock()
        self._maximum=failure_ceiling
        self._failures=0
        self._open=False
        self._revision=0

    def admit(self):
        with self._lock:
            if self._open:fail("native inference circuit open")
            return {"epoch":self._revision,"failure_count":self._failures}

    def success(self):
        with self._lock:
            if self._open:fail("open circuit cannot infer success")
            self._failures=0
            self._revision+=1
            return {"status":"closed","revision":self._revision}

    def failure(self):
        with self._lock:
            self._failures+=1
            if self._failures>=self._maximum:self._open=True
            self._revision+=1
            return {"status":"open" if self._open else "closed",
                    "failure_count":self._failures,"revision":self._revision}

    def reset(self,*,operator_approval,expected_revision):
        if operator_approval is not True:fail("operator must authorize circuit reset")
        if type(expected_revision) is not int:fail("stale or unknown circuit epoch")
        with self._lock:
            if expected_revision!=self._revision:fail("circuit reset compare-and-set conflict")
            if not self._open:fail("closed circuit does not require reset")
            self._open=False
            self._failures=0
            self._revision+=1
            return {"status":"closed","revision":self._revision,
                    "operator_approved":True}

    def snapshot(self):
        with self._lock:return {"open":self._open,"failures":self._failures,
                               "revision":self._revision,"failure_ceiling":self._maximum}
