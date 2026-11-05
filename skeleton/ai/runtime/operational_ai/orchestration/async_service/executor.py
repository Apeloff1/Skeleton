"""Process-local worker control; authoritative chat remains OfflineAIService.

Operations can be tracked durably across process restarts, but unknown in-flight
model generations are NEVER silently replayed. Restart requires explicit
operator reconciliation because the model response might have been committed.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import deque
from concurrent.futures import ThreadPoolExecutor,Future
import secrets,threading,time
from typing import Any
from ...persistence.durable.database import DurableDatabase,DurableError
from ...persistence.durable.operations import OperationRepository
from ...persistence.durable.eventlog import OperationEvents
from ...authority.identity import require_id

@dataclass(frozen=True,slots=True)
class JobReceipt:
    job_id:str
    session_id:str
    request_id:str
    state:str
    operation_version:int
    result:dict|None
    message:str

class AsyncAIExecutor:
    def __init__(self,service:Any,db:DurableDatabase,*,workers:int=2,
                 waiting_limit:int=64):
        if type(workers) is not int or not 1<=workers<=16:
            raise DurableError('invalid finite inference worker count')
        if type(waiting_limit) is not int or not workers<=waiting_limit<=1000:
            raise DurableError('invalid bounded waiting limit')
        self.service=service;self.db=db;self.repo=OperationRepository(db)
        self.events=OperationEvents(db);self._lock=threading.RLock()
        self._pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='skeleton-ai')
        self._capacity=threading.BoundedSemaphore(waiting_limit)
        self._futures={};self._cancelled=set();self._closed=False

    def submit(self,*,session:str,request_id:str,question:str,seed:int=0,
               temperature:float=1.0)->JobReceipt:
        require_id(session,field='session');require_id(request_id,field='request')
        if not isinstance(question,str) or not 1<=len(question.encode())<=32768:
            raise DurableError('invalid finite AI question')
        if not self._capacity.acquire(blocking=False):raise DurableError('AI job queue exhausted')
        operation='req_'+request_id
        payload={'session':session,'request_id':request_id,'question':question,
                 'seed':seed,'temperature':temperature}
        try:
            with self._lock:
                if self._closed:raise DurableError('AI executor draining')
                prior=self.repo.get(self.service.actor.tenant,self.service.actor.user,operation) if self._exists(operation) else None
                created=self.repo.create(self.service.actor.tenant,self.service.actor.user,operation,payload)
                if prior is not None:
                    self._capacity.release()
                    return self.get(request_id)
                self.events.append(created.tenant,created.owner,created.operation,
                    'enqueued','queued',{'session':session,'request_id':request_id})
                future=self._pool.submit(self._work,created,session,request_id,question,seed,temperature)
                self._futures[request_id]=future
                return JobReceipt(operation,session,request_id,created.state,created.version,None,'accepted')
        except BaseException:
            self._capacity.release()
            raise

    def _exists(self,operation:str)->bool:
        try:self.repo.get(self.service.actor.tenant,self.service.actor.user,operation);return True
        except DurableError:return False

    def _work(self,record,session,request_id,question,seed,temperature):
        try:
            with self._lock:
                current=self.repo.get(record.tenant,record.owner,record.operation)
                if record.operation in self._cancelled:
                    self.repo.change(record.tenant,record.owner,record.operation,
                         expected_version=current.version,state='cancelled')
                    return
                current=self.repo.change(record.tenant,record.owner,record.operation,
                                         expected_version=current.version,state='running')
            try:
                response=self.service.turn(session=session,request_id=request_id,question=question,
                                           seed=seed,temperature=temperature)
                payload=response.to_record()
                state='succeeded'
            except Exception as exc:
                # The service may have committed a response before raising;
                # report uncertainty and never automatically replay unknown effects.
                payload={'reason':'native-generation-or-commit-uncertain','detail':str(exc)[:200]}
                state='failed'
            current=self.repo.change(record.tenant,record.owner,record.operation,
                                     expected_version=current.version,state=state,result=payload)
            self.events.append(record.tenant,record.owner,record.operation,
                   'final_'+state,state,{'result_sha':self._result_sha(payload),'version':current.version})
        finally:
            self._capacity.release()

    @staticmethod
    def _result_sha(payload:dict)->str:
        import hashlib,json
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

    def get(self,request_id:str)->JobReceipt:
        require_id(request_id,field='request')
        op=self.repo.get(self.service.actor.tenant,self.service.actor.user,'req_'+request_id)
        return JobReceipt(op.operation,str(op.payload['session']),request_id,op.state,
                         op.version,op.result,'committed' if op.state=='succeeded' else op.state)

    def cancel(self,request_id:str)->JobReceipt:
        require_id(request_id,field='request')
        with self._lock:
            current=self.repo.get(self.service.actor.tenant,self.service.actor.user,'req_'+request_id)
            if current.state!='admitted':
                raise DurableError('cannot cancel running or terminal native effect; request drain')
            self._cancelled.add(current.operation)
            # Worker will commit cancellation in the same-order state transition.
            return self.get(request_id)

    def close(self,*,wait:bool=True):
        with self._lock:self._closed=True
        self._pool.shutdown(wait=wait,cancel_futures=False)

    def __enter__(self):return self
    def __exit__(self,*_:object):self.close()
