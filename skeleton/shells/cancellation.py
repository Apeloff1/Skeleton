"""Cooperative cancellation primitives for shell orchestration.

Cancellation is advisory until a caller actively checks a token. The low-level
ShellRunner remains responsible for terminating child processes on timeout and
output limits. Higher layers can use these tokens to refuse new attempts,
pipelines, or scheduled work before process creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable


class CancellationReason(str,Enum):
    USER="user"
    DEADLINE="deadline"
    SHUTDOWN="shutdown"
    SUPERSEDED="superseded"
    DEPENDENCY="dependency"
    POLICY="policy"
    INTERNAL="internal"


@dataclass(frozen=True)
class CancellationState:
    cancelled:bool
    reason:CancellationReason|None=None
    detail:str=""
    cancelled_at:float|None=None

    def to_dict(self)->dict[str,object]:
        return {
            "cancelled":self.cancelled,
            "reason":None if self.reason is None else self.reason.value,
            "detail":self.detail,
            "cancelled_at":self.cancelled_at,
        }


class CancellationError(RuntimeError):
    def __init__(self,state:CancellationState)->None:
        self.state=state
        reason="cancelled" if state.reason is None else state.reason.value
        super().__init__(f"shell operation cancelled ({reason})")


class CancellationToken:
    def __init__(self,*,clock:Callable[[],float]=time.monotonic)->None:
        self._clock=clock
        self._state=CancellationState(False)
        self._event=threading.Event()
        self._lock=threading.RLock()

    def cancel(
        self,
        reason:CancellationReason=CancellationReason.USER,
        *,
        detail:str="",
    )->bool:
        if len(detail)>512:raise ValueError("cancellation detail too long")
        reason=CancellationReason(reason)
        with self._lock:
            if self._state.cancelled:return False
            self._state=CancellationState(True,reason,detail,self._clock())
            self._event.set()
            return True

    @property
    def cancelled(self)->bool:return self._event.is_set()

    def snapshot(self)->CancellationState:
        with self._lock:return self._state

    def require_active(self)->None:
        state=self.snapshot()
        if state.cancelled:raise CancellationError(state)

    def wait(self,timeout:float|None=None)->bool:
        if timeout is not None and timeout<0:raise ValueError("timeout may not be negative")
        return self._event.wait(timeout)


class CancellationRegistry:
    """Bounded named cancellation-token registry."""

    def __init__(self,*,max_tokens:int=10000,clock:Callable[[],float]=time.monotonic)->None:
        if max_tokens<=0:raise ValueError("max_tokens must be positive")
        self.max_tokens=max_tokens
        self._clock=clock
        self._tokens:dict[str,CancellationToken]={}
        self._lock=threading.RLock()

    def create(self,key:str)->CancellationToken:
        if not key or len(key)>256:raise ValueError("invalid cancellation key")
        with self._lock:
            if key in self._tokens:raise RuntimeError("cancellation key already exists")
            if len(self._tokens)>=self.max_tokens:raise RuntimeError("cancellation registry capacity exhausted")
            token=CancellationToken(clock=self._clock)
            self._tokens[key]=token
            return token

    def get(self,key:str)->CancellationToken|None:
        with self._lock:return self._tokens.get(key)

    def require(self,key:str)->CancellationToken:
        token=self.get(key)
        if token is None:raise KeyError(key)
        return token

    def cancel(self,key:str,reason:CancellationReason=CancellationReason.USER,*,detail:str="")->bool:
        return self.require(key).cancel(reason,detail=detail)

    def remove(self,key:str,*,require_cancelled:bool=False)->bool:
        with self._lock:
            token=self._tokens.get(key)
            if token is None:return False
            if require_cancelled and not token.cancelled:
                raise RuntimeError("active cancellation token cannot be removed")
            del self._tokens[key]
            return True

    def cancelled(self)->tuple[str,...]:
        with self._lock:return tuple(sorted(key for key,value in self._tokens.items() if value.cancelled))

    def snapshot(self)->dict[str,CancellationState]:
        with self._lock:return {key:self._tokens[key].snapshot() for key in sorted(self._tokens)}
