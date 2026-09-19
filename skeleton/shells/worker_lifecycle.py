"""Strict lifecycle state machine for worker process wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable


class LifecycleState(str,Enum):
    NEW="new"
    REGISTERED="registered"
    STARTING="starting"
    READY="ready"
    DRAINING="draining"
    STOPPING="stopping"
    STOPPED="stopped"
    FAILED="failed"


_ALLOWED={
    LifecycleState.NEW:{LifecycleState.REGISTERED,LifecycleState.FAILED},
    LifecycleState.REGISTERED:{LifecycleState.STARTING,LifecycleState.STOPPING,LifecycleState.FAILED},
    LifecycleState.STARTING:{LifecycleState.READY,LifecycleState.STOPPING,LifecycleState.FAILED},
    LifecycleState.READY:{LifecycleState.DRAINING,LifecycleState.STOPPING,LifecycleState.FAILED},
    LifecycleState.DRAINING:{LifecycleState.READY,LifecycleState.STOPPING,LifecycleState.FAILED},
    LifecycleState.STOPPING:{LifecycleState.STOPPED,LifecycleState.FAILED},
    LifecycleState.STOPPED:set(),
    LifecycleState.FAILED:{LifecycleState.STOPPING,LifecycleState.STOPPED},
}


@dataclass(frozen=True)
class LifecycleTransition:
    sequence:int
    previous:LifecycleState
    current:LifecycleState
    observed_at:float
    reason:str=""

    def to_dict(self)->dict[str,object]:
        return {
            "sequence":self.sequence,
            "previous":self.previous.value,
            "current":self.current.value,
            "observed_at":self.observed_at,
            "reason":self.reason,
        }


class WorkerLifecycle:
    def __init__(self,*,clock:Callable[[],float]=time.monotonic,max_history:int=1000)->None:
        if max_history<=0:
            raise ValueError("max_history must be positive")
        self._clock=clock
        self.max_history=max_history
        self._state=LifecycleState.NEW
        self._history:list[LifecycleTransition]=[]
        self._lock=threading.RLock()

    @property
    def state(self)->LifecycleState:
        with self._lock:
            return self._state

    def can_transition(self,target:LifecycleState)->bool:
        target=LifecycleState(target)
        with self._lock:
            return target in _ALLOWED[self._state]

    def transition(self,target:LifecycleState,*,reason:str="")->LifecycleTransition:
        target=LifecycleState(target)
        if len(reason)>512:
            raise ValueError("transition reason too long")
        with self._lock:
            if target not in _ALLOWED[self._state]:
                raise RuntimeError(f"invalid worker lifecycle transition {self._state.value}->{target.value}")
            transition=LifecycleTransition(
                sequence=len(self._history)+1,
                previous=self._state,
                current=target,
                observed_at=self._clock(),
                reason=reason,
            )
            self._state=target
            self._history.append(transition)
            if len(self._history)>self.max_history:
                self._history=self._history[-self.max_history:]
            return transition

    def history(self)->tuple[LifecycleTransition,...]:
        with self._lock:
            return tuple(self._history)

    def fail(self,reason:str)->LifecycleTransition:
        return self.transition(LifecycleState.FAILED,reason=reason)

    def request_stop(self,reason:str="")->LifecycleTransition:
        with self._lock:
            if self._state is LifecycleState.STOPPED:
                raise RuntimeError("worker is already stopped")
            if self._state is LifecycleState.STOPPING:
                raise RuntimeError("worker is already stopping")
        return self.transition(LifecycleState.STOPPING,reason=reason)
