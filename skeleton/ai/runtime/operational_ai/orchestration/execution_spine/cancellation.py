"""Cooperative cancellation is a hold unless the current fence owns its state."""
from __future__ import annotations
from dataclasses import dataclass
import threading,time
from .contracts import Cancelled,Conflict,SpineError

@dataclass(frozen=True,slots=True)
class CancellationPolicy:
    deadline_ns:int
    def __post_init__(self):
        if type(self.deadline_ns)is not int or self.deadline_ns<=0:
            raise SpineError('invalid monotonic deadline')

class Cancellation:
    def __init__(self,*,deadline_ms:int):
        if type(deadline_ms)is not int or not 1<=deadline_ms<=600000:
            raise SpineError('invalid cancellation deadline')
        self._deadline=time.monotonic_ns()+deadline_ms*1_000_000
        self._event=threading.Event()
    def cancel(self):self._event.set()
    def check(self):
        if self._event.is_set():raise Cancelled('caller cancelled operation')
        if time.monotonic_ns()>=self._deadline:raise Cancelled('operation deadline expired')
    def remaining_ms(self):
        self.check()
        return max(1,(self._deadline-time.monotonic_ns())//1_000_000)
