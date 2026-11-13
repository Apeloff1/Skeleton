"""Pre-native idempotency key lease with pending-operation holds.

This reduces accidental concurrent duplicates, but native exactly-once custody
is still enforced by the authoritative durable ExecutionSpine requests table.
"""
from __future__ import annotations
from contextlib import contextmanager
from threading import RLock
from .contracts import identifier,refuse

class OnceGuard:
    def __init__(self,maximum=1024):
        if type(maximum) is not int or not 1<=maximum<=100000:
            refuse("invalid concurrent request capacity")
        self._lock=RLock();self._pending=set();self._max=maximum

    @contextmanager
    def hold(self,tenant,session,request):
        key=(identifier(tenant),identifier(session),identifier(request))
        with self._lock:
            if key in self._pending:refuse("concurrent duplicate live inference")
            if len(self._pending)>=self._max:refuse("active admission capacity exhausted")
            self._pending.add(key)
        try:yield
        finally:
            with self._lock:self._pending.discard(key)

    def snapshot(self):
        with self._lock:return {"pending":len(self._pending),"max":self._max}
