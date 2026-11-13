"""Concurrency slots, deadline admission and lock-safe drainage."""
from __future__ import annotations
from contextlib import contextmanager
from threading import Condition,Event
import time
from .contracts import ServingError

class Slots:
    def __init__(self,capacity:int=1):
        if type(capacity) is not int or not 1<=capacity<=64:
            raise ServingError('invalid physical slot ceiling')
        self.capacity=capacity
        self.used=0
        self._cond=Condition()
        self._draining=False

    @contextmanager
    def admitted(self,deadline_ns:int,cancel:Event|None=None):
        with self._cond:
            while self.used>=self.capacity:
                remaining=(deadline_ns-time.monotonic_ns())/1e9
                if remaining<=0 or (cancel and cancel.is_set()):
                    raise ServingError('serving admission timeout or cancellation')
                if self._draining:raise ServingError('serving draining')
                self._cond.wait(min(.05,remaining))
            if self._draining or time.monotonic_ns()>=deadline_ns:
                raise ServingError('serving admission unavailable')
            if cancel and cancel.is_set():raise ServingError('serving cancelled')
            self.used+=1
        try:yield
        finally:
            with self._cond:
                self.used-=1
                self._cond.notify_all()

    def drain(self)->None:
        with self._cond:
            self._draining=True
            self._cond.notify_all()

    def wait_empty(self,deadline_ns:int)->None:
        with self._cond:
            while self.used:
                left=(deadline_ns-time.monotonic_ns())/1e9
                if left<=0:raise ServingError('serving drain timeout')
                self._cond.wait(min(left,.1))
