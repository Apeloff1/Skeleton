"""Round-robin tenant scheduler; bounded admission, stable order and starvation prevention."""
from __future__ import annotations
from collections import deque,defaultdict
from dataclasses import dataclass
import threading
from .graph import WorkflowError

@dataclass(frozen=True,slots=True)
class QueueItem:
    tenant:str
    operation:str
    priority:int
    sequence:int

class FairAdmissionQueue:
    def __init__(self,*,capacity:int=4096,per_tenant:int=128):
        if any(type(v) is not int or not 1<=v<=65536 for v in (capacity,per_tenant)):
            raise WorkflowError('invalid scheduler bounds')
        self.capacity=capacity;self.per_tenant=per_tenant
        self._queues=defaultdict(deque);self._tenants=deque();self._seen=set()
        self._lock=threading.RLock();self._sequence=0

    def enqueue(self,tenant:str,operation:str,priority:int=0)->QueueItem:
        if not isinstance(tenant,str) or not 1<=len(tenant)<=128 or not isinstance(operation,str) or not 1<=len(operation)<=128:
            raise WorkflowError('invalid queued task identity')
        if type(priority) is not int or not 0<=priority<=10:
            raise WorkflowError('invalid queue priority')
        with self._lock:
            key=(tenant,operation)
            if key in self._seen:raise WorkflowError('duplicate queued task')
            if len(self._seen)>=self.capacity or len(self._queues[tenant])>=self.per_tenant:
                raise WorkflowError('admission queue at capacity')
            self._sequence+=1
            item=QueueItem(tenant,operation,priority,self._sequence)
            if not self._queues[tenant]:self._tenants.append(tenant)
            self._queues[tenant].append(item);self._seen.add(key)
            return item

    def pop(self)->QueueItem|None:
        with self._lock:
            if not self._tenants:return None
            tenant=self._tenants.popleft()
            # Priority is local to tenant, bounded to avoid cross-tenant starvation.
            q=self._queues[tenant]
            index=max(range(len(q)),key=lambda i:(q[i].priority,-q[i].sequence))
            item=q[index];del q[index]
            self._seen.remove((tenant,item.operation))
            if q:self._tenants.append(tenant)
            else:del self._queues[tenant]
            return item

    def __len__(self)->int:
        with self._lock:return len(self._seen)
