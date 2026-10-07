"""Revisioned in-memory worker state store with compare-and-swap updates."""

from __future__ import annotations

from dataclasses import dataclass,field
import hashlib
import json
import threading
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class WorkerStateRecord:
    worker_id:str
    generation:int
    revision:int
    values:Mapping[str,object]=field(default_factory=dict)
    digest:str=""

    def __post_init__(self)->None:
        if not self.worker_id or len(self.worker_id)>128:raise ValueError("invalid worker_id")
        if self.generation<=0 or self.revision<=0:raise ValueError("generation/revision must be positive")
        payload=dict(self.values)
        if len(payload)>128:raise ValueError("worker state has too many fields")
        try:json.dumps(payload,sort_keys=True,separators=(",",":"))
        except (TypeError,ValueError) as exc:raise ValueError("worker state must be JSON serializable") from exc
        object.__setattr__(self,"values",MappingProxyType(payload))

    def unsigned(self)->dict[str,object]:
        return {
            "worker_id":self.worker_id,
            "generation":self.generation,
            "revision":self.revision,
            "values":dict(self.values),
        }

    def expected_digest(self)->str:
        raw=json.dumps(self.unsigned(),sort_keys=True,separators=(",",":")).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def valid(self)->bool:return bool(self.digest) and self.digest==self.expected_digest()


class StateConflict(RuntimeError):pass


class WorkerStateStore:
    def __init__(self,*,max_workers:int=4096)->None:
        self.max_workers=max_workers
        self._items:dict[str,WorkerStateRecord]={}
        self._lock=threading.RLock()

    def put(
        self,
        worker_id:str,
        generation:int,
        values:Mapping[str,object],
        *,
        expected_revision:int|None=None,
    )->WorkerStateRecord:
        with self._lock:
            current=self._items.get(worker_id)
            if current is None:
                if expected_revision not in (None,0):
                    raise StateConflict("worker state does not exist")
                if len(self._items)>=self.max_workers:
                    raise StateConflict("worker state capacity exhausted")
                revision=1
            else:
                if generation<current.generation:
                    raise StateConflict("worker state generation rollback")
                if generation>current.generation:
                    if expected_revision not in (None,0):
                        raise StateConflict("new generation must start from revision zero")
                    revision=1
                else:
                    if expected_revision is not None and expected_revision!=current.revision:
                        raise StateConflict("worker state revision conflict")
                    revision=current.revision+1
            provisional=WorkerStateRecord(worker_id,generation,revision,values)
            record=WorkerStateRecord(worker_id,generation,revision,values,provisional.expected_digest())
            self._items[worker_id]=record
            return record

    def get(self,worker_id:str)->WorkerStateRecord|None:
        with self._lock:return self._items.get(worker_id)

    def compare_and_swap(
        self,
        worker_id:str,
        generation:int,
        expected_revision:int,
        values:Mapping[str,object],
    )->WorkerStateRecord:
        return self.put(worker_id,generation,values,expected_revision=expected_revision)

    def delete(self,worker_id:str,*,generation:int|None=None,revision:int|None=None)->bool:
        with self._lock:
            current=self._items.get(worker_id)
            if current is None:return False
            if generation is not None and current.generation!=generation:return False
            if revision is not None and current.revision!=revision:return False
            del self._items[worker_id]
            return True

    def snapshot(self)->tuple[WorkerStateRecord,...]:
        with self._lock:return tuple(sorted(self._items.values(),key=lambda item:item.worker_id))
