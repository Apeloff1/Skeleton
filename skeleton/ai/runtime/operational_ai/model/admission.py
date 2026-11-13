"""Finite native inference admission; no unbounded queueing or silent fallback."""
from __future__ import annotations
from contextlib import contextmanager
import threading
import time
from typing import Iterator
from ..authority.canonical import ContractViolation


class InferenceAdmission:
    def __init__(self,*,workers:int=1,max_waiting:int=4):
        if any(type(v) is not int or not 1<=v<=64 for v in (workers,max_waiting)):
            raise ContractViolation("invalid inference concurrency admission")
        self._slots=threading.BoundedSemaphore(workers)
        self._queued=threading.BoundedSemaphore(max_waiting)
        self._active=0
        self._lock=threading.Lock()
        self.workers=workers

    @contextmanager
    def slot(self,*,deadline_ns:int,cancel:threading.Event|None=None)->Iterator[None]:
        if type(deadline_ns) is not int or deadline_ns<=0:
            raise ContractViolation("invalid inference deadline")
        if not self._queued.acquire(blocking=False):
            raise ContractViolation("model admission queue saturated")
        claimed=False
        try:
            while not claimed:
                if cancel is not None and cancel.is_set():
                    raise ContractViolation("inference cancelled before admission")
                remaining=(deadline_ns-time.monotonic_ns())/1_000_000_000
                if remaining<=0:
                    raise ContractViolation("inference admission timed out")
                claimed=self._slots.acquire(timeout=min(remaining,0.05))
            with self._lock:
                self._active+=1
            try:
                if cancel is not None and cancel.is_set():
                    raise ContractViolation("inference cancelled")
                yield
            finally:
                with self._lock:
                    self._active-=1
                self._slots.release()
        finally:
            self._queued.release()

    @property
    def active(self)->int:
        with self._lock:
            return self._active
