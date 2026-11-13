"""Explicit allowlist-only operator telemetry and bounded aggregation."""
from __future__ import annotations
from threading import RLock
from ..contracts import fail
from skeleton.ai.runtime.operational_ai.laptop_runtime.privacy import safe_record

class PrivateMetrics:
    def __init__(self,maximum=1000000):
        if type(maximum) is not int or not 1<=maximum<=10000000:
            fail("unbounded telemetry maximum")
        self._max=maximum;self._lock=RLock()
        self._counts={"ok":0,"held":0,"failed":0}
        self._observations=0

    def observe(self,source,*,outcome):
        if outcome not in self._counts:
            fail("unsupported observed outcome")
        redacted=safe_record(source)
        with self._lock:
            if self._observations>=self._max:
                fail("telemetry cap reached")
            self._observations+=1
            self._counts[outcome]+=1
            # Do not retain source fields, prompts, tokens, bearer or paths.
            return {"outcome":outcome,"sample":self._observations,
                    "input_fields_persisted":0}

    def snapshot(self):
        with self._lock:
            return {"samples":self._observations,"counts":dict(self._counts),
                    "raw_prompt_bytes_retained":0,
                    "private_tokens_retained":0}
