"""Partition-safe distributed execution contracts for VOL-102."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class DistributedError(ValueError):pass
class OutcomeState(str,Enum): PENDING="pending"; SUCCEEDED="succeeded"; FAILED="failed"; UNKNOWN_EXTERNAL="unknown_external"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise DistributedError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise DistributedError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class DistributedTask:
 task_id:str;payload_digest:str;idempotency_key:str;external_effect:bool
 def __post_init__(self):
  object.__setattr__(self,"task_id",_id(self.task_id,"task_id"));object.__setattr__(self,"idempotency_key",_id(self.idempotency_key,"idempotency_key"));_sha(self.payload_digest,"payload_digest")
  if not isinstance(self.external_effect,bool):raise DistributedError("external_effect must be bool")
 @property
 def digest(self):return _dig({"task_id":self.task_id,"payload":self.payload_digest,"idempotency":self.idempotency_key,"external_effect":self.external_effect})
@dataclass(frozen=True,slots=True)
class WorkerLease:
 lease_id:str;task_digest:str;worker_id:str;fence_token:int
 def __post_init__(self):
  for f in ("lease_id","worker_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  _sha(self.task_digest,"task_digest")
  if isinstance(self.fence_token,bool) or not isinstance(self.fence_token,int) or self.fence_token<1:raise DistributedError("fence token invalid")
@dataclass(frozen=True,slots=True)
class DistributedReceipt:
 task_digest:str;lease_id:str;fence_token:int;state:OutcomeState;result_digest:str|None;provider_evidence_digest:str|None
 def __post_init__(self):
  _sha(self.task_digest,"task_digest");object.__setattr__(self,"lease_id",_id(self.lease_id,"lease_id"))
  if not isinstance(self.fence_token,int) or isinstance(self.fence_token,bool) or self.fence_token<1:raise DistributedError("receipt fence token invalid")
  if not isinstance(self.state,OutcomeState):raise DistributedError("state must be OutcomeState")
  if self.result_digest is not None:_sha(self.result_digest,"result_digest")
  if self.provider_evidence_digest is not None:_sha(self.provider_evidence_digest,"provider_evidence_digest")
  if self.state is OutcomeState.SUCCEEDED and self.result_digest is None:raise DistributedError("success requires result")
  if self.state is OutcomeState.UNKNOWN_EXTERNAL and self.provider_evidence_digest is not None:raise DistributedError("unknown outcome cannot claim provider evidence")
class DistributedScheduler:
 def __init__(self):self._fence={};self._active={};self._terminal={};self._idempotency={}
 def _bind_task(self,task):
  if not isinstance(task,DistributedTask):raise DistributedError("task must be DistributedTask")
  prior=self._idempotency.get(task.idempotency_key)
  if prior is not None and prior!=task.digest:raise DistributedError("idempotency key reused for different task")
  self._idempotency[task.idempotency_key]=task.digest
 def lease(self,task,worker_id):
  self._bind_task(task)
  if task.task_id in self._terminal:return None
  token=self._fence.get(task.task_id,0)+1;self._fence[task.task_id]=token
  lease=WorkerLease(f"LEASE.{task.task_id}.{token}",task.digest,worker_id,token);self._active[task.task_id]=lease;return lease
 def commit(self,task,lease,state,*,result_digest=None,provider_evidence_digest=None):
  active=self._active.get(task.task_id)
  if active!=lease or lease.task_digest!=task.digest:raise DistributedError("stale or mismatched worker lease")
  prior=self._terminal.get(task.task_id)
  receipt=DistributedReceipt(task.digest,lease.lease_id,lease.fence_token,state,result_digest,provider_evidence_digest)
  if prior is not None and prior!=receipt:raise DistributedError("terminal outcome immutable")
  if state in (OutcomeState.SUCCEEDED,OutcomeState.FAILED):
   self._terminal[task.task_id]=receipt;self._active.pop(task.task_id,None)
  return receipt
 def worker_lost(self,task,lease,effect_may_have_escaped):
  if not isinstance(effect_may_have_escaped,bool):raise DistributedError("effect_may_have_escaped must be bool")
  if effect_may_have_escaped and not task.external_effect:raise DistributedError("non-external task cannot report escaped effect")
  if self._active.get(task.task_id)!=lease:raise DistributedError("stale worker loss report")
  if task.external_effect and effect_may_have_escaped:
   return self.commit(task,lease,OutcomeState.UNKNOWN_EXTERNAL)
  self._active.pop(task.task_id,None);return None
 def reconcile(self,task,unknown,*,provider_evidence_digest,result_digest=None,failed=False):
  self._bind_task(task)
  if unknown.task_digest!=task.digest:raise DistributedError("receipt/task mismatch")
  active=self._active.get(task.task_id)
  if active is not None and (active.lease_id!=unknown.lease_id or active.fence_token!=unknown.fence_token):raise DistributedError("unknown receipt is not authoritative active lease")
  if unknown.state is not OutcomeState.UNKNOWN_EXTERNAL:raise DistributedError("reconciliation requires unknown outcome")
  _sha(provider_evidence_digest,"provider_evidence_digest")
  state=OutcomeState.FAILED if failed else OutcomeState.SUCCEEDED
  if state is OutcomeState.SUCCEEDED and result_digest is None:raise DistributedError("successful reconciliation requires result")
  receipt=DistributedReceipt(task.digest,unknown.lease_id,unknown.fence_token,state,result_digest,provider_evidence_digest)
  prior=self._terminal.get(task.task_id)
  if prior is not None and prior!=receipt:raise DistributedError("terminal outcome immutable")
  self._terminal[task.task_id]=receipt;self._active.pop(task.task_id,None);return receipt
 def may_reissue(self,task):
  return task.task_id not in self._terminal and task.task_id not in self._active
