"""Conservative local-model fault gate; no implicit alternate provider routing."""
from __future__ import annotations
import threading
import time
from ..authority.canonical import ContractViolation


class CircuitOpen(ContractViolation):
    """A failing model was taken out of admission pending retry interval."""


class CircuitBreaker:
    def __init__(self,*,max_consecutive_failures:int=3,cooldown_ms:int=30000):
        if type(max_consecutive_failures) is not int or not 1<=max_consecutive_failures<=100:
            raise ContractViolation("invalid failure threshold")
        if type(cooldown_ms) is not int or not 1<=cooldown_ms<=3600000:
            raise ContractViolation("invalid failure cooldown")
        self.maximum=max_consecutive_failures
        self.cooldown_ns=cooldown_ms*1_000_000
        self._failures=0
        self._opened_at: int | None=None
        self._lock=threading.Lock()

    def admit(self)->None:
        with self._lock:
            if self._opened_at is None:
                return
            if time.monotonic_ns()-self._opened_at<self.cooldown_ns:
                raise CircuitOpen("local inference circuit open; no hosted fallback")
            # One transition to probing, then fail closed until a generation
            # confirms recovery or the failure threshold reopens the circuit.
            self._opened_at=None
            self._failures=self.maximum-1

    def success(self)->None:
        with self._lock:
            self._failures=0
            self._opened_at=None

    def failure(self)->None:
        with self._lock:
            self._failures=min(self.maximum,self._failures+1)
            if self._failures>=self.maximum:
                self._opened_at=time.monotonic_ns()

    @property
    def health(self)->dict[str,int|bool]:
        with self._lock:
            return {"failures":self._failures,"open":self._opened_at is not None,
                    "max_consecutive_failures":self.maximum}
