"""Immutable model epoch and fail-closed identity fences."""
from __future__ import annotations
from threading import RLock
from .contracts import ModelIdentity,ServingError

class EpochFence:
    def __init__(self,identity:ModelIdentity):
        self._lock=RLock()
        self._identity=identity
        self._in_flight=0

    @property
    def current(self)->ModelIdentity:
        with self._lock:return self._identity

    def acquire(self,expected:ModelIdentity)->None:
        with self._lock:
            if expected!=self._identity:raise ServingError('model epoch drift')
            self._in_flight+=1

    def release(self)->None:
        with self._lock:
            if self._in_flight<=0:raise ServingError('unbalanced model lease')
            self._in_flight-=1

    def replace(self,new:ModelIdentity)->None:
        with self._lock:
            if self._in_flight:raise ServingError('cannot change model while in flight')
            if new.epoch<=self._identity.epoch:raise ServingError('model epoch must increase')
            self._identity=new
