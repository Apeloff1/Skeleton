"""Cap reader backlog independently of model execution."""
from __future__ import annotations
from collections import deque
from threading import Lock
from .contracts import ServingError

class BoundedResponses:
    def __init__(self,maximum:int=128):
        if type(maximum) is not int or not 1<=maximum<=4096:raise ServingError('response queue invalid')
        self._maximum=maximum;self._q=deque();self._lock=Lock()

    def publish(self,record:bytes)->None:
        if not isinstance(record,bytes) or len(record)>262144:
            raise ServingError('response exceeds wire limit')
        with self._lock:
            if len(self._q)>=self._maximum:raise ServingError('slow consumer backpressure')
            self._q.append(record)

    def consume(self)->bytes|None:
        with self._lock:return self._q.popleft() if self._q else None
