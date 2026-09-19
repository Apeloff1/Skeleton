"""Worker fault classification and bounded fault history."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable


class WorkerFailureKind(str,Enum):
    COMMAND="command"
    TIMEOUT="timeout"
    OUTPUT_LIMIT="output_limit"
    ADMISSION="admission"
    LEASE="lease"
    QUEUE_TRANSITION="queue_transition"
    HEARTBEAT="heartbeat"
    RESOURCE="resource"
    INTERNAL="internal"


@dataclass(frozen=True)
class WorkerFailure:
    worker_id:str
    generation:int
    kind:WorkerFailureKind
    observed_at:float
    retryable:bool=False
    detail:str=""

    def __post_init__(self)->None:
        if not self.worker_id or len(self.worker_id)>128:raise ValueError("invalid worker_id")
        if self.generation<=0:raise ValueError("generation must be positive")
        if len(self.detail)>512:raise ValueError("failure detail too long")


class WorkerFailureLog:
    def __init__(self,*,max_items:int=10000,clock:Callable[[],float]=time.monotonic)->None:
        self.max_items=max_items
        self._clock=clock
        self._items:list[WorkerFailure]=[]
        self._lock=threading.RLock()

    def record(
        self,
        worker_id:str,
        generation:int,
        kind:WorkerFailureKind,
        *,
        retryable:bool=False,
        detail:str="",
    )->WorkerFailure:
        with self._lock:
            failure=WorkerFailure(worker_id,generation,WorkerFailureKind(kind),self._clock(),retryable,detail)
            self._items.append(failure)
            if len(self._items)>self.max_items:
                del self._items[:len(self._items)-self.max_items]
            return failure

    def recent(
        self,
        *,
        worker_id:str|None=None,
        kind:WorkerFailureKind|None=None,
        since:float=0.0,
    )->tuple[WorkerFailure,...]:
        with self._lock:
            return tuple(
                item for item in self._items
                if item.observed_at>=since
                and (worker_id is None or item.worker_id==worker_id)
                and (kind is None or item.kind is kind)
            )

    def count(self,**kwargs)->int:
        return len(self.recent(**kwargs))
