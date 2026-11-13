"""Bounded redacted operation statistics; never record prompts or auth tokens."""
from __future__ import annotations
from threading import RLock
from .contracts import identifier,integer,refuse
class Metrics:
    def __init__(self,*,maximum=10000000):
        integer(maximum,minimum=1,maximum=100000000)
        self._max=maximum;self._lock=RLock();self._n=0
        self._counters={}
        self._durations={}
    def observe(self,domain,outcome,duration_ms):
        identifier(domain);identifier(outcome)
        integer(duration_ms,maximum=3600000)
        if outcome not in ("accepted","rejected","held","failed","replayed"):
            refuse("telemetry outcome is not allowlisted")
        with self._lock:
            if self._n>=self._max:refuse("telemetry capacity reached")
            key=(domain,outcome)
            self._n+=1;self._counters[key]=self._counters.get(key,0)+1
            totals=self._durations.get(domain,(0,0))
            self._durations[domain]=(totals[0]+duration_ms,totals[1]+1)
            return {"domain":domain,"outcome":outcome,"samples":self._n}
    def snapshot(self):
        with self._lock:
            return {"sample_count":self._n,
                "counts":{k[0]+":"+k[1]:v for k,v in self._counters.items()},
                "average_ms":{k:s/max(1,n) for k,(s,n) in self._durations.items()},
                "user_prompt_logged":False,"operator_keys_logged":False}
