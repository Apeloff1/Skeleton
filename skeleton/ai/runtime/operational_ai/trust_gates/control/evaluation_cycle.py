"""Counts-only evaluation ledger scoped to one pinned dataset and model.

This ledger does not score, train, certify or promote a model.
"""
from __future__ import annotations
from threading import RLock
from ..contracts import fail
from ..engine import validate

class EvaluationCycle:
    def __init__(self,suite_id,dataset_sha,model_sha,*,maximum_samples=1000000):
        if type(maximum_samples) is not int or not 1<=maximum_samples<=100000000:
            fail("invalid evaluation sample ceiling")
        self.suite_id=suite_id;self.dataset_sha=dataset_sha;self.model_sha=model_sha
        self._lock=RLock()
        self._max=maximum_samples;self._pass=0;self._fail=0;self._error=0
        self._closed=False

    def observe(self,outcome):
        if outcome not in ("pass","fail","empty-error"):
            fail("ambiguous evaluation outcome")
        with self._lock:
            if self._closed: fail("evaluation already closed")
            if self._pass+self._fail+self._error>=self._max:
                fail("evaluation sample limit exhausted")
            if outcome=="pass": self._pass+=1
            elif outcome=="fail": self._fail+=1
            else: self._error+=1

    def snapshot(self):
        with self._lock:
            return {"samples":self._pass+self._fail+self._error,
                    "passes":self._pass,"failures":self._fail,
                    "empty_errors":self._error,"closed":self._closed}

    def close(self,*,approved=False):
        with self._lock:
            if self._closed: fail("already sealed evaluation")
            result=validate("evaluation",{
                "suite_id":self.suite_id,"dataset_sha":self.dataset_sha,
                "model_sha":self.model_sha,"samples":self._pass+self._fail+self._error,
                "passes":self._pass,"failures":self._fail,"empty_errors":self._error,
                "approved":approved})
            self._closed=True
            return result
