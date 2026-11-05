"""Bounded tenant-fair inference queue with idempotent request conflicts."""
from __future__ import annotations
from collections import deque,defaultdict
from dataclasses import dataclass
import threading
from .workers import WorkerError

@dataclass(frozen=True,slots=True)
class InferenceJob:
    tenant:str
    request_id:str
    model_sha:str
    cost_tokens:int
    priority:int
    ordinal:int

class TenantFairQueue:
    def __init__(self,*,max_waiting:int=2048,per_tenant:int=128):
        if type(max_waiting) is not int or not 1<=max_waiting<=65536 or type(per_tenant) is not int or not 1<=per_tenant<=65536:
            raise WorkerError('invalid queue ceilings')
        self.max_waiting=max_waiting;self.per_tenant=per_tenant
        self._lock=threading.RLock();self._groups=defaultdict(deque);self._rotation=deque();self._seen={};self._ordinal=0

    def put(self,tenant:str,request_id:str,model_sha:str,cost_tokens:int,priority:int=0)->InferenceJob:
        if type(cost_tokens) is not int or not 1<=cost_tokens<=131072 or type(priority) is not int or not 0<=priority<=10:
            raise WorkerError('invalid inference job budget')
        with self._lock:
            key=(tenant,request_id)
            if key in self._seen:
                if self._seen[key].model_sha!=model_sha or self._seen[key].cost_tokens!=cost_tokens:
                    raise WorkerError('queued request id reused with different model or cost')
                return self._seen[key]
            if len(self._seen)>=self.max_waiting or len(self._groups[tenant])>=self.per_tenant:
                raise WorkerError('inference waiting queue full')
            self._ordinal+=1
            job=InferenceJob(tenant,request_id,model_sha,cost_tokens,priority,self._ordinal)
            if not self._groups[tenant]:self._rotation.append(tenant)
            self._groups[tenant].append(job);self._seen[key]=job
            return job

    def pop(self)->InferenceJob|None:
        with self._lock:
            if not self._rotation:return None
            tenant=self._rotation.popleft()
            q=self._groups[tenant]
            best=max(range(len(q)),key=lambda i:(q[i].priority,-q[i].ordinal))
            job=q[best];del q[best];del self._seen[(tenant,job.request_id)]
            if q:self._rotation.append(tenant)
            else:del self._groups[tenant]
            return job

    def __len__(self)->int:
        with self._lock:return len(self._seen)
