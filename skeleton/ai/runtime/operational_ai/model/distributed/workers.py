"""Observed worker availability tied to immutable model bytes and process epochs."""
from __future__ import annotations
from dataclasses import dataclass
import re,threading,time

class WorkerError(ValueError):pass
_SHA=re.compile(r'^[0-9a-f]{64}$')
_ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')

@dataclass(frozen=True,slots=True)
class Worker:
    worker_id:str
    model_sha:str
    tokenizer_sha:str
    epoch:int
    capacity_tokens:int
    active_tokens:int
    memory_headroom_bytes:int
    last_seen_ns:int
    state:str
    locality:str
    def __post_init__(self):
        if not _ID.fullmatch(self.worker_id) or not _SHA.fullmatch(self.model_sha) or not _SHA.fullmatch(self.tokenizer_sha):
            raise WorkerError('worker lacks pinned identity')
        if any(type(v) is not int or v<0 for v in (self.epoch,self.capacity_tokens,self.active_tokens,
                                                   self.memory_headroom_bytes,self.last_seen_ns)):
            raise WorkerError('worker capacity counters invalid')
        if self.active_tokens>self.capacity_tokens:raise WorkerError('worker admitted more than capacity')
        if self.state not in {'ready','draining','offline','suspect'}:raise WorkerError('invalid worker lifecycle')
        if self.locality not in {'local-process','local-host'}:
            raise WorkerError('remote worker identity requires separate explicit authority')

class WorkerRegistry:
    def __init__(self,*,timeout_ns:int=30_000_000_000,limit:int=1024):
        if type(timeout_ns) is not int or not 1_000_000<=timeout_ns<=3600_000_000_000:
            raise WorkerError('invalid heartbeat expiry')
        if type(limit) is not int or not 1<=limit<=10000:raise WorkerError('invalid registry capacity')
        self.timeout_ns=timeout_ns;self.limit=limit;self._lock=threading.RLock();self._workers={}

    def heartbeat(self,worker:Worker)->None:
        with self._lock:
            old=self._workers.get(worker.worker_id)
            if old:
                if worker.epoch<old.epoch or (worker.epoch==old.epoch and worker.last_seen_ns<=old.last_seen_ns):
                    raise WorkerError('stale worker heartbeat or epoch')
                if worker.epoch==old.epoch and (worker.model_sha,worker.tokenizer_sha)!=(old.model_sha,old.tokenizer_sha):
                    raise WorkerError('worker model switched without new process epoch')
            if len(self._workers)>=self.limit and not old:raise WorkerError('worker registry full')
            self._workers[worker.worker_id]=worker

    def candidates(self,*,now_ns:int|None=None)->tuple[Worker,...]:
        now=time.monotonic_ns() if now_ns is None else now_ns
        with self._lock:
            return tuple(sorted((x for x in self._workers.values() if x.state=='ready'
                and x.last_seen_ns<=now and now-x.last_seen_ns<=self.timeout_ns),key=lambda x:x.worker_id))

    def mark_draining(self,worker_id:str)->Worker:
        with self._lock:
            x=self._workers.get(worker_id)
            if x is None:raise WorkerError('worker missing')
            new=Worker(x.worker_id,x.model_sha,x.tokenizer_sha,x.epoch,x.capacity_tokens,x.active_tokens,
                x.memory_headroom_bytes,x.last_seen_ns,'draining',x.locality)
            self._workers[worker_id]=new;return new
