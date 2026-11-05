"""Local model fault circuit, based on backend failures not answer quality."""
from __future__ import annotations
import time,threading
from .contracts import Busy,SpineError

class RuntimeCircuit:
    def __init__(self,*,failure_limit:int=3,cooldown_s:float=30):
        if type(failure_limit)is not int or not 1<=failure_limit<=100:raise SpineError('invalid failure threshold')
        if type(cooldown_s)not in (int,float) or not 0<cooldown_s<=3600:raise SpineError('invalid cooldown')
        self._threshold=failure_limit;self._cooldown_ns=int(cooldown_s*1e9)
        self._faults=0;self._open_ns=0;self._probe=False;self._lock=threading.Lock()
    def allow(self):
        with self._lock:
            if self._open_ns:
                if time.monotonic_ns()<self._open_ns:raise Busy('model circuit breaker open')
                if self._probe:raise Busy('model circuit half-open trial in progress')
                self._probe=True
    def success(self):
        with self._lock:self._faults=0;self._open_ns=0;self._probe=False
    def failure(self):
        with self._lock:
            self._faults+=1;self._probe=False
            if self._faults>=self._threshold:self._open_ns=time.monotonic_ns()+self._cooldown_ns
    def status(self):
        with self._lock:return {'state':'open' if self._open_ns and time.monotonic_ns()<self._open_ns else ('half-open' if self._open_ns else 'closed'),
            'failures':self._faults}
