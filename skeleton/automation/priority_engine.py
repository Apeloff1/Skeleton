"""Transparent bounded priority engine for VOL-094."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class PriorityError(ValueError):pass
class ConstraintKind(str,Enum): HARD_BLOCKER="hard_blocker"; SOFT_SIGNAL="soft_signal"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise PriorityError(f"{f} must be stable identifier")
 return v
def _digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class PriorityInput:
 factor_id:str;provenance_ref:str;value:float;weight:float
 def __post_init__(self):
  object.__setattr__(self,"factor_id",_id(self.factor_id,"factor_id"));object.__setattr__(self,"provenance_ref",_id(self.provenance_ref,"provenance_ref"))
  for f in ("value","weight"):
   v=getattr(self,f)
   if not isinstance(v,(int,float)) or isinstance(v,bool):raise PriorityError(f"{f} must be numeric")
  if not 0<=self.value<=1:raise PriorityError("value must be bounded 0..1")
  if not -10<=self.weight<=10:raise PriorityError("weight must be bounded -10..10")
 @property
 def contribution(self):return self.value*self.weight

@dataclass(frozen=True,slots=True)
class PriorityConstraint:
 constraint_id:str;kind:ConstraintKind;active:bool;provenance_ref:str;reason:str
 def __post_init__(self):
  object.__setattr__(self,"constraint_id",_id(self.constraint_id,"constraint_id"));object.__setattr__(self,"provenance_ref",_id(self.provenance_ref,"provenance_ref"))
  if not isinstance(self.reason,str) or not self.reason.strip():raise PriorityError("constraint reason required")

@dataclass(frozen=True,slots=True)
class PriorityDecision:
 item_id:str;blocked:bool;score:float;effective_score:float;factor_ids:tuple[str,...];blocker_ids:tuple[str,...];age_boost:float
 @property
 def digest(self):return _digest({"item_id":self.item_id,"blocked":self.blocked,"score":self.score,"effective_score":self.effective_score,"factor_ids":self.factor_ids,"blocker_ids":self.blocker_ids,"age_boost":self.age_boost})

class PriorityEngine:
 def __init__(self,*,max_age_boost:float=5.0,age_step:float=.1,hysteresis:float=.25):
  if not 0<=max_age_boost<=10 or not 0<=age_step<=1 or not 0<=hysteresis<=5:raise PriorityError("engine bounds invalid")
  self.max_age_boost=max_age_boost;self.age_step=age_step;self.hysteresis=hysteresis
 def decide(self,item_id:str,inputs, constraints=(),*,age_epochs:int=0,previous_score:float|None=None)->PriorityDecision:
  _id(item_id,"item_id")
  factors=tuple(sorted(inputs,key=lambda x:x.factor_id)); blockers=tuple(sorted(c.constraint_id for c in constraints if c.kind is ConstraintKind.HARD_BLOCKER and c.active))
  if len({f.factor_id for f in factors})!=len(factors):raise PriorityError("duplicate priority factor")
  if age_epochs<0:raise PriorityError("age_epochs cannot be negative")
  raw=sum(f.contribution for f in factors)
  age=min(self.max_age_boost,age_epochs*self.age_step)
  target=raw+age
  effective=target
  if previous_score is not None and abs(target-previous_score)<self.hysteresis:effective=previous_score
  return PriorityDecision(item_id,bool(blockers),round(raw,8),round(effective,8),tuple(f.factor_id for f in factors),blockers,round(age,8))
 def rank(self,decisions):
  items=tuple(decisions)
  if len({d.item_id for d in items})!=len(items):raise PriorityError("duplicate decision item")
  return tuple(sorted(items,key=lambda d:(d.blocked,-d.effective_score,d.item_id)))
