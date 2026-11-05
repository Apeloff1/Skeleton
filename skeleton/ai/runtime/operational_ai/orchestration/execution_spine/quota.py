"""Resource quota by owner/model, with bounded reservations and fairness."""
from __future__ import annotations
import threading, time
from contextlib import contextmanager
from .contracts import Identity,SpineError,Busy

class Quota:
    def __init__(self,*,max_active_total:int=8,max_per_principal:int=2):
        if any(type(x)is not int or not 1<=x<=1024 for x in (max_active_total,max_per_principal)):
            raise SpineError('invalid execution quota')
        if max_per_principal>max_active_total:raise SpineError('tenant concurrency exceeds capacity')
        self.total=max_active_total;self.per=max_per_principal
        self._lock=threading.RLock();self._busy={};self._active=0

    @contextmanager
    def reserve(self,identity:Identity):
        if not isinstance(identity,Identity):raise SpineError('identity required')
        key=identity.key()
        with self._lock:
            if self._active>=self.total or self._busy.get(key,0)>=self.per:
                raise Busy('bounded resource quota exhausted')
            self._active+=1;self._busy[key]=self._busy.get(key,0)+1
        try:yield
        finally:
            with self._lock:
                self._active-=1;self._busy[key]-=1
                if not self._busy[key]:del self._busy[key]
    def snapshot(self):
        with self._lock:return {'active':self._active,'max_active':self.total,'principals':len(self._busy)}
