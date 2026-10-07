"""Bounded shell failure ledger with low-cardinality classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable

class ShellFailureKind(str,Enum):
    POLICY="policy"
    CAPABILITY="capability"
    ARGUMENT="argument"
    ENVIRONMENT="environment"
    WORKSPACE="workspace"
    TIMEOUT="timeout"
    OUTPUT_LIMIT="output_limit"
    RETURN_CODE="return_code"
    CIRCUIT="circuit"
    RATE_LIMIT="rate_limit"
    BUDGET="budget"
    CONCURRENCY="concurrency"
    CANCELLATION="cancellation"
    INTERNAL="internal"

@dataclass(frozen=True)
class ShellFailureRecord:
    sequence:int
    observed_at:float
    command:str
    correlation_id:str
    kind:ShellFailureKind
    retryable:bool=False
    detail:str=""

    def __post_init__(self)->None:
        if self.sequence<=0:
            raise ValueError("failure sequence must be positive")
        if not self.command or len(self.command)>128:
            raise ValueError("invalid failure command")
        if len(self.correlation_id)>160:
            raise ValueError("correlation_id too long")
        if len(self.detail)>512:
            raise ValueError("failure detail too long")

    def to_dict(self)->dict[str,object]:
        return {
            "sequence":self.sequence,
            "observed_at":self.observed_at,
            "command":self.command,
            "correlation_id":self.correlation_id,
            "kind":self.kind.value,
            "retryable":self.retryable,
            "detail":self.detail,
        }

class ShellFailureLedger:
    def __init__(
        self,
        *,
        max_records:int=10000,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        if max_records<=0:
            raise ValueError("max_records must be positive")
        self.max_records=max_records
        self._clock=clock
        self._records:list[ShellFailureRecord]=[]
        self._sequence=0
        self._lock=threading.RLock()

    def record(
        self,
        command:str,
        kind:ShellFailureKind,
        *,
        correlation_id:str="",
        retryable:bool=False,
        detail:str="",
    )->ShellFailureRecord:
        with self._lock:
            self._sequence+=1
            item=ShellFailureRecord(
                self._sequence,self._clock(),command,correlation_id,
                ShellFailureKind(kind),retryable,detail,
            )
            self._records.append(item)
            if len(self._records)>self.max_records:
                del self._records[:len(self._records)-self.max_records]
            return item

    def query(
        self,
        *,
        command:str|None=None,
        kind:ShellFailureKind|None=None,
        retryable:bool|None=None,
        after_sequence:int=0,
    )->tuple[ShellFailureRecord,...]:
        with self._lock:
            return tuple(
                item for item in self._records
                if item.sequence>after_sequence
                and (command is None or item.command==command)
                and (kind is None or item.kind is kind)
                and (retryable is None or item.retryable is retryable)
            )

    def counts(self)->dict[str,int]:
        result={kind.value:0 for kind in ShellFailureKind}
        with self._lock:
            for item in self._records:
                result[item.kind.value]+=1
        return result

    def tail(self,count:int=100)->tuple[ShellFailureRecord,...]:
        if count<=0:
            raise ValueError("count must be positive")
        with self._lock:
            return tuple(self._records[-count:])
