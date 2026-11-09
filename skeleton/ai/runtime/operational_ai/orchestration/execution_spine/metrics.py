"""Privacy-preserving bounded aggregate metrics; no user text or raw messages."""
from __future__ import annotations
from dataclasses import dataclass,field
from collections import Counter
import threading,time
from .contracts import SpineError
@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    calls:int
    successes:int
    failed:int
    replayed:int
    input_tokens:int
    output_tokens:int
    duration_ns:int
    held:int

class Metrics:
    def __init__(self):
        self._lock=threading.RLock()
        self._c=Counter()
    def observe(self,*,outcome:str,prompt_tokens:int=0,output_tokens:int=0,duration_ns:int=0):
        if outcome not in ('ok','failed','replayed','held'):raise SpineError('unsupported metric result')
        if any(type(v)is not int or v<0 or v>10**15 for v in (prompt_tokens,output_tokens,duration_ns)):
            raise SpineError('invalid bounded metric value')
        with self._lock:
            self._c['calls']+=1;self._c[outcome]+=1
            self._c['input_tokens']+=prompt_tokens
            self._c['output_tokens']+=output_tokens
            self._c['duration_ns']+=duration_ns
    def snapshot(self)->MetricSnapshot:
        with self._lock:
            c=self._c.copy()
        return MetricSnapshot(c['calls'],c['ok'],c['failed'],c['replayed'],
            c['input_tokens'],c['output_tokens'],c['duration_ns'],c['held'])
