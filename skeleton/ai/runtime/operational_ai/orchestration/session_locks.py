"""Bounded per-session in-process inference lease preventing duplicate retries.

The SQLite CAS remains the cross-process authority. This reduces duplicate
physical inference within one runtime process and provides strict deadlines,
without asserting that an in-process mutex is a distributed lock.
"""
from __future__ import annotations
from contextlib import contextmanager
import threading
import time
from typing import Iterator
from ..authority.canonical import ContractViolation
from ..authority.identity import require_id


class SessionLocks:
    def __init__(self,*,max_distinct_sessions:int=512):
        if type(max_distinct_sessions) is not int or not 1<=max_distinct_sessions<=4096:
            raise ContractViolation("invalid session-lock capacity")
        self.maximum=max_distinct_sessions
        self._lock=threading.Lock()
        self._sessions:dict[str,tuple[threading.Lock,int]]={}

    @contextmanager
    def reserve(self,session:str,*,deadline_ms:int=60000)->Iterator[None]:
        require_id(session,field="concurrent session")
        if type(deadline_ms) is not int or not 1<=deadline_ms<=86_400_000:
            raise ContractViolation("invalid session lock deadline")
        start=time.monotonic_ns()
        with self._lock:
            entry=self._sessions.get(session)
            if entry is None:
                if len(self._sessions)>=self.maximum:
                    raise ContractViolation("session lock capacity exhausted")
                entry=(threading.Lock(),0)
            lock,count=entry
            self._sessions[session]=(lock,count+1)
        claimed=False
        try:
            timeout=max(0.0,(deadline_ms*1_000_000-(time.monotonic_ns()-start))/1e9)
            claimed=lock.acquire(timeout=timeout)
            if not claimed:
                raise ContractViolation("concurrent session operation timed out")
            yield
        finally:
            if claimed:
                lock.release()
            with self._lock:
                registered,refs=self._sessions[session]
                if registered is not lock or refs<=0:
                    raise ContractViolation("session lock accounting corrupt")
                if refs==1:
                    del self._sessions[session]
                else:
                    self._sessions[session]=(lock,refs-1)

    @property
    def active_sessions(self)->int:
        with self._lock:
            return len(self._sessions)
