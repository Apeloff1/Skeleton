"""Bounded metadata cache for deterministic shell execution outcomes.

The cache stores only result metadata and digests, never stdout/stderr bytes.
Callers decide whether a command is safe to treat as deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import threading
import time
from typing import Callable

from skeleton.shells.runner import ShellResult


@dataclass(frozen=True)
class CachedExecution:
    fingerprint:str
    command:str
    returncode:int|None
    ok:bool
    timed_out:bool
    output_limited:bool
    stdout_bytes:int
    stderr_bytes:int
    stdout_digest:str
    stderr_digest:str
    stored_at:float
    expires_at:float
    hits:int=0

    @classmethod
    def from_result(
        cls,fingerprint:str,result:ShellResult,*,stored_at:float,ttl_seconds:float
    )->"CachedExecution":
        return cls(
            fingerprint,result.command,result.returncode,result.ok,result.timed_out,
            result.output_limited,len(result.stdout),len(result.stderr),
            hashlib.sha256(result.stdout).hexdigest(),hashlib.sha256(result.stderr).hexdigest(),
            stored_at,stored_at+ttl_seconds,0,
        )


class ExecutionCache:
    def __init__(
        self,
        *,
        max_entries:int=10000,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        if max_entries<=0:raise ValueError("max_entries must be positive")
        self.max_entries=max_entries
        self._clock=clock
        self._items:dict[str,CachedExecution]={}
        self._lock=threading.RLock()

    def _prune(self)->None:
        now=self._clock()
        for key in [key for key,value in self._items.items() if value.expires_at<=now]:
            del self._items[key]

    def put(self,fingerprint:str,result:ShellResult,*,ttl_seconds:float=60.0)->CachedExecution:
        if not fingerprint or len(fingerprint)>256:raise ValueError("invalid execution fingerprint")
        if ttl_seconds<=0:raise ValueError("ttl_seconds must be positive")
        with self._lock:
            self._prune()
            if fingerprint not in self._items and len(self._items)>=self.max_entries:
                # Deterministically evict the oldest entry.
                oldest=min(self._items.values(),key=lambda item:(item.stored_at,item.fingerprint))
                self._items.pop(oldest.fingerprint,None)
            now=self._clock()
            item=CachedExecution.from_result(fingerprint,result,stored_at=now,ttl_seconds=ttl_seconds)
            self._items[fingerprint]=item
            return item

    def get(self,fingerprint:str)->CachedExecution|None:
        with self._lock:
            self._prune()
            item=self._items.get(fingerprint)
            if item is None:return None
            touched=CachedExecution(
                item.fingerprint,item.command,item.returncode,item.ok,item.timed_out,
                item.output_limited,item.stdout_bytes,item.stderr_bytes,item.stdout_digest,
                item.stderr_digest,item.stored_at,item.expires_at,item.hits+1,
            )
            self._items[fingerprint]=touched
            return touched

    def invalidate(self,fingerprint:str)->bool:
        with self._lock:return self._items.pop(fingerprint,None) is not None

    def clear(self)->None:
        with self._lock:self._items.clear()

    def snapshot(self)->tuple[CachedExecution,...]:
        with self._lock:
            self._prune()
            return tuple(sorted(self._items.values(),key=lambda item:item.fingerprint))
