"""Exclusive lease contract for bounded ownership transfer."""
from __future__ import annotations
from dataclasses import dataclass
from threading import Lock
@dataclass
class Lease:
    token:str
    _released:bool=False
    def release(self)->None:
        if self._released: raise RuntimeError("lease already released")
        self._released=True
class LeaseSet:
    def __init__(self,capacity:int=64):
        if capacity<=0: raise ValueError("capacity must be positive")
        self._cap=capacity; self._active=0; self._lock=Lock()
    def acquire(self,token:str)->Lease|None:
        with self._lock:
            if self._active>=self._cap: return None
            self._active+=1
        lease=Lease(token); original=lease.release
        def release():
            original()
            with self._lock: self._active-=1
        lease.release=release
        return lease
    @property
    def active(self)->int: return self._active
