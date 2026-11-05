"""Worker token allocation with epoch fencing and explicit finalization."""
from __future__ import annotations
from dataclasses import dataclass
import threading
from .workers import WorkerError

@dataclass(frozen=True,slots=True)
class WorkerLease:
    worker_id:str
    epoch:int
    fence:int
    request_id:str
    reserved_tokens:int

class WorkerFences:
    def __init__(self):
        self._lock=threading.RLock();self._epochs={};self._leases={};self._sequences={}

    def reset(self,worker_id:str,epoch:int)->None:
        with self._lock:
            old=self._epochs.get(worker_id,-1)
            if epoch<=old:raise WorkerError('worker generation must advance')
            self._epochs[worker_id]=epoch
            self._leases={k:v for k,v in self._leases.items() if v.worker_id!=worker_id}
            self._sequences[worker_id]=0

    def admit(self,worker_id:str,epoch:int,request_id:str,tokens:int)->WorkerLease:
        if type(tokens) is not int or not 1<=tokens<=131072:
            raise WorkerError('invalid token allocation')
        with self._lock:
            if self._epochs.get(worker_id)!=epoch:raise WorkerError('stale worker epoch')
            key=(worker_id,request_id)
            if key in self._leases:raise WorkerError('duplicate worker request allocation')
            self._sequences[worker_id]+=1
            lease=WorkerLease(worker_id,epoch,self._sequences[worker_id],request_id,tokens)
            self._leases[key]=lease;return lease

    def verify(self,lease:WorkerLease)->bool:
        with self._lock:
            return self._epochs.get(lease.worker_id)==lease.epoch and self._leases.get((lease.worker_id,lease.request_id))==lease

    def release(self,lease:WorkerLease)->None:
        with self._lock:
            if not self.verify(lease):raise WorkerError('stale worker lease completion')
            del self._leases[(lease.worker_id,lease.request_id)]
