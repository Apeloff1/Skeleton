"""Bounded multi-agent coordination contracts for VOL-100."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class CoordinationError(ValueError):pass
class AgentState(str,Enum): ASSIGNED="assigned"; HANDED_OFF="handed_off"; FAILED="failed"; VERIFIED="verified"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise CoordinationError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise CoordinationError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class MultiAgentTask:
 task_id:str;objective:str;authority_ids:tuple[str,...];scope_paths:tuple[str,...];max_agents:int
 def __post_init__(self):
  object.__setattr__(self,"task_id",_id(self.task_id,"task_id"))
  if not isinstance(self.objective,str) or not self.objective.strip():raise CoordinationError("objective required")
  object.__setattr__(self,"objective",self.objective.strip())
  for f in ("authority_ids","scope_paths"):
   raw=getattr(self,f)
   if not isinstance(raw,tuple) or len(raw)>256:raise CoordinationError(f"{f} must be bounded tuple")
   vals=tuple(sorted(set(raw)))
   if not vals:raise CoordinationError(f"{f} required")
   object.__setattr__(self,f,vals)
  if isinstance(self.max_agents,bool) or not isinstance(self.max_agents,int) or not 1<=self.max_agents<=32:raise CoordinationError("max_agents out of bounds")
 @property
 def digest(self):return _dig({"task_id":self.task_id,"objective":self.objective,"authority_ids":self.authority_ids,"scope_paths":self.scope_paths,"max_agents":self.max_agents})
@dataclass(frozen=True,slots=True)
class AgentAssignment:
 assignment_id:str;task_digest:str;agent_id:str;authority_ids:tuple[str,...];scope_paths:tuple[str,...];lease_id:str
 def __post_init__(self):
  for f in ("assignment_id","agent_id","lease_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  _sha(self.task_digest,"task_digest")
  for f in ("authority_ids","scope_paths"):
   raw=getattr(self,f)
   if not isinstance(raw,tuple) or not raw or len(raw)>256:raise CoordinationError(f"{f} must be non-empty bounded tuple")
   object.__setattr__(self,f,tuple(sorted(set(raw))))
@dataclass(frozen=True,slots=True)
class HandoffPacket:
 handoff_id:str;assignment_id:str;producer_id:str;artifact_digest:str;state_digest:str;test_digest:str;rollback_ref:str
 def __post_init__(self):
  for f in ("handoff_id","assignment_id","producer_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  for f in ("artifact_digest","state_digest","test_digest"):_sha(getattr(self,f),f)
  if not self.rollback_ref.strip():raise CoordinationError("rollback_ref required")
 @property
 def digest(self):return _dig({"handoff_id":self.handoff_id,"assignment_id":self.assignment_id,"producer_id":self.producer_id,"artifact_digest":self.artifact_digest,"state_digest":self.state_digest,"test_digest":self.test_digest,"rollback_ref":self.rollback_ref})
@dataclass(frozen=True,slots=True)
class HandoffVerification:
 handoff_digest:str;verifier_id:str;producer_id:str;passed:bool
 def __post_init__(self):
  _sha(self.handoff_digest,"handoff_digest");object.__setattr__(self,"verifier_id",_id(self.verifier_id,"verifier_id"));object.__setattr__(self,"producer_id",_id(self.producer_id,"producer_id"))
  if not isinstance(self.passed,bool):raise CoordinationError("passed must be bool")
  if self.verifier_id==self.producer_id:raise CoordinationError("handoff verifier must be independent")
class Coordinator:
 def __init__(self,task):
  if not isinstance(task,MultiAgentTask):raise CoordinationError("task must be MultiAgentTask")
  self.task=task;self.assignments={};self.failed=set();self.handoffs={}
 def assign(self,a):
  if not isinstance(a,AgentAssignment):raise CoordinationError("assignment must be AgentAssignment")
  if a.task_digest!=self.task.digest:raise CoordinationError("assignment/task mismatch")
  if not set(a.authority_ids)<=set(self.task.authority_ids):raise CoordinationError("delegated authority exceeds parent")
  if not set(a.scope_paths)<=set(self.task.scope_paths):raise CoordinationError("delegated scope exceeds parent")
  if a.assignment_id in self.assignments and self.assignments[a.assignment_id]!=a:raise CoordinationError("assignment identity immutable")
  if len(self.assignments)>=self.task.max_agents and a.assignment_id not in self.assignments:raise CoordinationError("agent budget exhausted")
  for prior in self.assignments.values():
   if prior.assignment_id!=a.assignment_id and set(prior.scope_paths)&set(a.scope_paths):raise CoordinationError("mutation conflict domain overlaps")
  self.assignments[a.assignment_id]=a
 def accept_handoff(self,p):
  if not isinstance(p,HandoffPacket):raise CoordinationError("handoff must be HandoffPacket")
  a=self.assignments.get(p.assignment_id)
  if a is None:raise CoordinationError("handoff references unknown assignment")
  if p.producer_id!=a.agent_id:raise CoordinationError("handoff producer mismatch")
  prior=self.handoffs.get(p.assignment_id)
  if prior is not None and prior.digest!=p.digest:raise CoordinationError("handoff identity immutable for assignment")
  self.handoffs[p.assignment_id]=p;return p.digest
 def fail(self,assignment_id):
  if assignment_id not in self.assignments:raise CoordinationError("unknown assignment")
  self.failed.add(assignment_id)
 def recover(self,assignment_id,replacement):
  if assignment_id not in self.failed:raise CoordinationError("assignment is not failed")
  prior=self.assignments[assignment_id]
  if not isinstance(replacement,AgentAssignment):raise CoordinationError("replacement must be AgentAssignment")
  if replacement.assignment_id!=assignment_id or replacement.task_digest!=self.task.digest:raise CoordinationError("replacement identity mismatch")
  if replacement.agent_id==prior.agent_id or replacement.lease_id==prior.lease_id:raise CoordinationError("recovery requires new agent and lease")
  if replacement.authority_ids!=prior.authority_ids or replacement.scope_paths!=prior.scope_paths:raise CoordinationError("recovery cannot amplify or alter delegated domain")
  self.assignments[assignment_id]=replacement;self.failed.remove(assignment_id);self.handoffs.pop(assignment_id,None)
 def can_commit(self,verifications):
  if not isinstance(verifications,tuple) or any(not isinstance(v,HandoffVerification) for v in verifications):raise CoordinationError("verifications must be typed tuple")
  if self.failed or not self.assignments or set(self.handoffs)!=set(self.assignments):return False
  by_digest={v.handoff_digest:v for v in verifications if v.passed}
  if len(by_digest)!=len(verifications):return False
  for h in self.handoffs.values():
   v=by_digest.get(h.digest)
   if v is None or v.producer_id!=h.producer_id:return False
  return len(by_digest)==len(self.assignments)
