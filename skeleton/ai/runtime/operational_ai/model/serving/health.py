"""Model health state determined by observed real successes and failures."""
from __future__ import annotations
from collections import deque
from threading import Lock
from .contracts import ServingError

class HealthWindow:
    def __init__(self,width:int=64,minimum_success_ratio:float=.85):
        if not 1<=width<=1024 or not 0<minimum_success_ratio<=1:raise ServingError('invalid health window')
        self._history=deque(maxlen=width);self._lock=Lock();self.minimum=minimum_success_ratio

    def record(self,success:bool):
        if type(success) is not bool:raise ServingError('health record must be boolean')
        with self._lock:self._history.append(success)

    def snapshot(self)->dict:
        with self._lock:
            n=len(self._history);s=sum(self._history)
        return {'samples':n,'successes':s,'healthy':n>0 and s/n>=self.minimum}
