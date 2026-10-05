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
  if not self.objective.strip():raise CoordinationError("objective required")
  for f in ("authority_ids","scope_paths"):
   vals=tuple(sorted(set(getattr(self,f))))
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
  object.__setattr__(self,"authority_ids",tuple(sorted(set(self.authority_ids))));object.__setattr__(self,"scope_paths",tuple(sorted(set(self.scope_paths))))
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
  if self.verifier_id==self.producer_id:raise CoordinationError("handoff verifier must be independent")
class Coordinator:
 def __init__(self,task):self.task=task;self.assignments={};self.failed=set()
 def assign(self,a):
  if a.task_digest!=self.task.digest:raise CoordinationError("assignment/task mismatch")
  if not set(a.authority_ids)<=set(self.task.authority_ids):raise CoordinationError("delegated authority exceeds parent")
  if not set(a.scope_paths)<=set(self.task.scope_paths):raise CoordinationError("delegated scope exceeds parent")
  if a.assignment_id in self.assignments and self.assignments[a.assignment_id]!=a:raise CoordinationError("assignment identity immutable")
  if len(self.assignments)>=self.task.max_agents and a.assignment_id not in self.assignments:raise CoordinationError("agent budget exhausted")
  for prior in self.assignments.values():
   if prior.assignment_id!=a.assignment_id and set(prior.scope_paths)&set(a.scope_paths):raise CoordinationError("mutation conflict domain overlaps")
  self.assignments[a.assignment_id]=a
 def accept_handoff(self,p):
  a=self.assignments.get(p.assignment_id)
  if a is None:raise CoordinationError("handoff references unknown assignment")
  if p.producer_id!=a.agent_id:raise CoordinationError("handoff producer mismatch")
  return p.digest
 def fail(self,assignment_id):
  if assignment_id not in self.assignments:raise CoordinationError("unknown assignment")
  self.failed.add(assignment_id)
 def can_commit(self,verifications):
  verified={v.handoff_digest for v in verifications if v.passed}
  return not self.failed and bool(self.assignments) and len(verified)==len(self.assignments)
