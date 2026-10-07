"""Mutation-custody contracts for the VOL-098 engineering agent."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class EngineeringError(ValueError):pass
class LeaseState(str,Enum): ACTIVE="active"; RELEASED="released"; FENCED="fenced"
class VerificationDecision(str,Enum): PASS="pass"; FAIL="fail"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise EngineeringError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise EngineeringError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class EngineeringTask:
 task_id:str;objective:str;repository_digest:str;scope_paths:tuple[str,...];test_refs:tuple[str,...];rollback_ref:str
 def __post_init__(self):
  object.__setattr__(self,"task_id",_id(self.task_id,"task_id"));_sha(self.repository_digest,"repository_digest")
  if not isinstance(self.objective,str) or not self.objective.strip():raise EngineeringError("objective required")
  object.__setattr__(self,"objective",self.objective.strip())
  for f in ("scope_paths","test_refs"):
   raw=getattr(self,f)
   if not isinstance(raw,tuple):raise EngineeringError(f"{f} must be tuple")
   if len(raw)>256:raise EngineeringError(f"{f} exceeds policy bound")
   vals=tuple(sorted(set(raw)))
   if not vals or any(not isinstance(v,str) or not v.strip() for v in vals):raise EngineeringError(f"{f} required")
   object.__setattr__(self,f,vals)
  if not self.rollback_ref.strip():raise EngineeringError("rollback_ref required")
 @property
 def digest(self):return _dig({"task_id":self.task_id,"objective":self.objective,"repository_digest":self.repository_digest,"scope_paths":self.scope_paths,"test_refs":self.test_refs,"rollback_ref":self.rollback_ref})
@dataclass(frozen=True,slots=True)
class MutationLease:
 lease_id:str;task_digest:str;holder_id:str;fence_token:int;scope_paths:tuple[str,...];state:LeaseState
 def __post_init__(self):
  for f in ("lease_id","holder_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  _sha(self.task_digest,"task_digest")
  if not isinstance(self.fence_token,int) or isinstance(self.fence_token,bool) or self.fence_token<1:raise EngineeringError("fence_token must be positive")
  if not isinstance(self.state,LeaseState):raise EngineeringError("state must be LeaseState")
  if not isinstance(self.scope_paths,tuple) or not self.scope_paths:raise EngineeringError("scope_paths must be non-empty tuple")
  object.__setattr__(self,"scope_paths",tuple(sorted(set(self.scope_paths))))
@dataclass(frozen=True,slots=True)
class ChangeRecord:
 change_id:str;task_digest:str;lease_id:str;fence_token:int;before_digest:str;after_digest:str;paths:tuple[str,...]
 def __post_init__(self):
  for f in ("change_id","lease_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  for f in ("task_digest","before_digest","after_digest"):_sha(getattr(self,f),f)
  if not isinstance(self.fence_token,int) or isinstance(self.fence_token,bool) or self.fence_token<1:raise EngineeringError("fence_token must be positive")
  if self.before_digest==self.after_digest:raise EngineeringError("change must alter repository state")
  if not isinstance(self.paths,tuple) or not self.paths:raise EngineeringError("paths must be non-empty tuple")
  object.__setattr__(self,"paths",tuple(sorted(set(self.paths))))
 @property
 def digest(self):return _dig({"change_id":self.change_id,"task_digest":self.task_digest,"lease_id":self.lease_id,"fence_token":self.fence_token,"before_digest":self.before_digest,"after_digest":self.after_digest,"paths":self.paths})
@dataclass(frozen=True,slots=True)
class EngineeringEvidence:
 evidence_id:str;task_digest:str;change_digest:str;builder_id:str;verifier_id:str;decision:VerificationDecision;test_digest:str;rollback_verified:bool
 def __post_init__(self):
  for f in ("evidence_id","builder_id","verifier_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  for f in ("task_digest","change_digest","test_digest"):_sha(getattr(self,f),f)
  if not isinstance(self.decision,VerificationDecision):raise EngineeringError("decision must be VerificationDecision")
  if not isinstance(self.rollback_verified,bool):raise EngineeringError("rollback_verified must be bool")
  if self.builder_id==self.verifier_id:raise EngineeringError("verifier must be independent from builder")
  if self.decision is VerificationDecision.PASS and not self.rollback_verified:raise EngineeringError("passing evidence requires verified rollback")
class MutationCustody:
 def __init__(self):self._latest={};self._active={}
 def acquire(self,task:EngineeringTask,holder_id:str)->MutationLease:
  holder_id=_id(holder_id,"holder_id");token=self._latest.get(task.task_id,0)+1;self._latest[task.task_id]=token
  old=self._active.get(task.task_id)
  if old is not None and old.state is LeaseState.ACTIVE:raise EngineeringError("task already has active mutation lease")
  lease=MutationLease(f"LEASE.{task.task_id}.{token}",task.digest,holder_id,token,task.scope_paths,LeaseState.ACTIVE);self._active[task.task_id]=lease;return lease
 def release(self,task:EngineeringTask,lease:MutationLease)->None:
  self.assert_authorized(task,lease,lease.scope_paths);self._active[task.task_id]=MutationLease(lease.lease_id,lease.task_digest,lease.holder_id,lease.fence_token,lease.scope_paths,LeaseState.RELEASED)
 def assert_authorized(self,task:EngineeringTask,lease:MutationLease,paths)->None:
  active=self._active.get(task.task_id)
  if active is None or active.state is not LeaseState.ACTIVE or active!=lease:raise EngineeringError("mutation lease is stale or inactive")
  if lease.task_digest!=task.digest:raise EngineeringError("lease/task mismatch")
  if any(not isinstance(p,str) or not p.strip() for p in paths):raise EngineeringError("mutation paths invalid")
  if not set(paths)<=set(lease.scope_paths):raise EngineeringError("mutation escapes leased scope")
 def record(self,task:EngineeringTask,lease:MutationLease,change_id:str,before:str,after:str,paths)->ChangeRecord:
  self.assert_authorized(task,lease,paths);return ChangeRecord(change_id,task.digest,lease.lease_id,lease.fence_token,before,after,tuple(paths))

@dataclass(frozen=True,slots=True)
class EngineeringAcceptance:
 task_digest:str;change_digest:str;evidence_digest:str
 def __post_init__(self):
  for f in ("task_digest","change_digest","evidence_digest"):_sha(getattr(self,f),f)
def accept_change(task:EngineeringTask,change:ChangeRecord,evidence:EngineeringEvidence)->EngineeringAcceptance:
 if not isinstance(task,EngineeringTask) or not isinstance(change,ChangeRecord) or not isinstance(evidence,EngineeringEvidence):raise EngineeringError("acceptance inputs must be typed")
 if change.task_digest!=task.digest or evidence.task_digest!=task.digest:raise EngineeringError("acceptance task identity mismatch")
 if evidence.change_digest!=change.digest:raise EngineeringError("evidence/change identity mismatch")
 if evidence.decision is not VerificationDecision.PASS:raise EngineeringError("failed verification cannot accept change")
 if not evidence.rollback_verified:raise EngineeringError("rollback must be verified")
 ed=_dig({"evidence_id":evidence.evidence_id,"task_digest":evidence.task_digest,"change_digest":evidence.change_digest,"builder_id":evidence.builder_id,"verifier_id":evidence.verifier_id,"decision":evidence.decision.value,"test_digest":evidence.test_digest,"rollback_verified":evidence.rollback_verified})
 return EngineeringAcceptance(task.digest,change.digest,ed)
