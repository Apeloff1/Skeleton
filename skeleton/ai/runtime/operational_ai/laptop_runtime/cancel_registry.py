"""Explicit per-request cooperative cancellation handles with no false kill claim."""
from __future__ import annotations
from threading import RLock
from .contracts import identifier,refuse

class CancellationRegistry:
    def __init__(self,maximum=128):
        if type(maximum) is not int or not 1<=maximum<=4096:
            refuse("invalid cancel registry bound")
        self._lock=RLock();self._max=maximum;self._active={}

    def register(self,session_id,request_id,*,deadline_ms):
        from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.cancellation import Cancellation
        key=(identifier(session_id),identifier(request_id))
        with self._lock:
            if key in self._active or len(self._active)>=self._max:
                refuse("request cancellation lease already active or full")
            cancel=Cancellation(deadline_ms=deadline_ms)
            self._active[key]=cancel
            return cancel

    def cancel(self,session_id,request_id):
        key=(identifier(session_id),identifier(request_id))
        with self._lock:
            obj=self._active.get(key)
            if obj is None:refuse("unknown live cancellation handle")
            obj.cancel()
            # Cooperative signal only. Native subprocess cancellation and
            # restart-recovery must be independently observed and certified.
            return {"cooperative_cancel_requested":True,
                    "native_process_terminated_proved":False}

    def retire(self,session_id,request_id,cancel):
        key=(identifier(session_id),identifier(request_id))
        with self._lock:
            if self._active.get(key) is not cancel:
                refuse("cancellation lease owner mismatch")
            del self._active[key]

    def snapshot(self):
        with self._lock:return {"active":len(self._active),"ceiling":self._max}
