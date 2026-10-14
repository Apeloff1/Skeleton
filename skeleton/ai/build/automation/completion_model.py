"""Deterministic derived completion rollups for VOL-119."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class CompletionError(ValueError):pass
class CompletionState(str,Enum): PENDING="pending";PARTIAL="partial";BLOCKED="blocked";COMPLETE="complete"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise CompletionError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise CompletionError(f"{f} must be sha256")
 return v
@dataclass(frozen=True,slots=True)
class AtomicCompletion:
 accountability_id:str;state:CompletionState;evidence_digest:str|None=None;signed:bool=False;signoff_tick:int|None=None;source_tick:int=0
 def __post_init__(self):
  object.__setattr__(self,"accountability_id",_id(self.accountability_id,"accountability_id"))
  if not isinstance(self.state,CompletionState) or not isinstance(self.signed,bool):raise CompletionError("atomic completion types invalid")
  for n in ("source_tick","signoff_tick"):
   v=getattr(self,n)
   if v is not None and (not isinstance(v,int) or isinstance(v,bool) or v<0):raise CompletionError("completion ticks must be nonnegative integers")
  if self.state is CompletionState.COMPLETE:
   if not self.signed or self.evidence_digest is None or self.signoff_tick is None:raise CompletionError("complete state requires signed evidence")
   _sha(self.evidence_digest,"evidence_digest")
   if self.signoff_tick<self.source_tick:raise CompletionError("stale signoff")
  elif self.signed or self.evidence_digest is not None or self.signoff_tick is not None:raise CompletionError("non-complete state cannot carry completion signoff")
@dataclass(frozen=True,slots=True)
class CompletionBlocker:
 accountability_id:str;reason:str;critical:bool=True
 def __post_init__(self):
  object.__setattr__(self,"accountability_id",_id(self.accountability_id,"accountability_id"))
  if not isinstance(self.reason,str) or not self.reason.strip() or not isinstance(self.critical,bool):raise CompletionError("blocker must be reasoned and typed")
@dataclass(frozen=True,slots=True)
class CompletionRollup:
 state:CompletionState;completed:int;total:int;blocked_ids:tuple[str,...]
 @property
 def fraction(self):return self.completed/self.total
 @property
 def percent(self):return 100*self.fraction
def rollup(records,blockers=()):
 if not isinstance(records,tuple) or not records or any(not isinstance(x,AtomicCompletion) for x in records):raise CompletionError("records must be non-empty typed tuple")
 if not isinstance(blockers,tuple) or any(not isinstance(x,CompletionBlocker) for x in blockers):raise CompletionError("blockers must be typed tuple")
 ids=[x.accountability_id for x in records]
 if len(set(ids))!=len(ids):raise CompletionError("duplicate accountability record")
 known=set(ids)
 if any(x.accountability_id not in known for x in blockers):raise CompletionError("blocker references unknown accountability")
 if len({(x.accountability_id,x.reason) for x in blockers})!=len(blockers):raise CompletionError("duplicate blocker")
 completed=sum(x.state is CompletionState.COMPLETE for x in records)
 blocked=tuple(sorted({x.accountability_id for x in blockers if x.critical}|{x.accountability_id for x in records if x.state is CompletionState.BLOCKED}))
 if blocked:state=CompletionState.BLOCKED
 elif completed==len(records):state=CompletionState.COMPLETE
 elif completed:state=CompletionState.PARTIAL
 else:state=CompletionState.PENDING
 return CompletionRollup(state,completed,len(records),blocked)
