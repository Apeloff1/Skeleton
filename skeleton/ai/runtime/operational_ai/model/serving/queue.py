"""Deterministic bounded round-robin queue by tenant."""
from __future__ import annotations
from collections import deque
from threading import Lock
from .contracts import ServingError,Request

class FairRequestQueue:
    def __init__(self,maximum:int=256,per_tenant:int=16):
        if type(maximum) is not int or type(per_tenant) is not int or not 1<=per_tenant<=maximum<=4096:
            raise ServingError('invalid fair queue ceiling')
        self.maximum=maximum;self.per_tenant=per_tenant
        self._items:dict[str,deque[Request]]={}
        self._turns:deque[str]=deque()
        self._seen:set[tuple[str,str]]=set()
        self._lock=Lock()

    def put(self,request:Request)->None:
        with self._lock:
            if (request.tenant,request.request_id) in self._seen:
                raise ServingError('duplicate queue request')
            if len(self._seen)>=self.maximum:raise ServingError('global admission queue full')
            q=self._items.setdefault(request.tenant,deque())
            if len(q)>=self.per_tenant:raise ServingError('tenant queue full')
            if not q:self._turns.append(request.tenant)
            q.append(request);self._seen.add((request.tenant,request.request_id))

    def get(self)->Request|None:
        with self._lock:
            if not self._turns:return None
            tenant=self._turns.popleft();q=self._items[tenant]
            item=q.popleft();self._seen.remove((item.tenant,item.request_id))
            if q:self._turns.append(tenant)
            else:del self._items[tenant]
            return item

    def __len__(self)->int:
        with self._lock:return len(self._seen)
