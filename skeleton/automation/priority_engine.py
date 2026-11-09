"""Transparent bounded priority engine for VOL-094."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re,math
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA=re.compile(r"^[0-9a-f]{64}$")
_MAX_FACTORS=256
_MAX_CONSTRAINTS=256
_MAX_RAW_SCORE=2560.0
_MIN_EFFECTIVE_SCORE=-2565.0
_MAX_EFFECTIVE_SCORE=2575.0
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
   if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v):raise PriorityError(f"{f} must be finite numeric")
  if not 0<=self.value<=1:raise PriorityError("value must be bounded 0..1")
  if not -10<=self.weight<=10:raise PriorityError("weight must be bounded -10..10")
 @property
 def contribution(self):return self.value*self.weight

@dataclass(frozen=True,slots=True)
class PriorityConstraint:
 constraint_id:str;kind:ConstraintKind;active:bool;provenance_ref:str;reason:str
 def __post_init__(self):
  object.__setattr__(self,"constraint_id",_id(self.constraint_id,"constraint_id"));object.__setattr__(self,"provenance_ref",_id(self.provenance_ref,"provenance_ref"))
  if not isinstance(self.kind,ConstraintKind):raise PriorityError("kind must be ConstraintKind")
  if not isinstance(self.active,bool):raise PriorityError("active must be bool")
  if not isinstance(self.reason,str) or not self.reason.strip():raise PriorityError("constraint reason required")

@dataclass(frozen=True,slots=True)
class PriorityDecision:
 item_id:str;blocked:bool;score:float;effective_score:float;factor_ids:tuple[str,...];blocker_ids:tuple[str,...];age_boost:float;input_digest:str
 def __post_init__(self):
  object.__setattr__(self,"item_id",_id(self.item_id,"item_id"))
  if not isinstance(self.blocked,bool):raise PriorityError("blocked must be bool")
  for f in ("score","effective_score","age_boost"):
   v=getattr(self,f)
   if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v):raise PriorityError(f"{f} must be finite numeric")
  if not -_MAX_RAW_SCORE<=self.score<=_MAX_RAW_SCORE:raise PriorityError("score exceeds derivable priority bound")
  if not _MIN_EFFECTIVE_SCORE<=self.effective_score<=_MAX_EFFECTIVE_SCORE:raise PriorityError("effective_score exceeds derivable priority bound")
  if not 0<=self.age_boost<=10:raise PriorityError("age_boost must be bounded 0..10")
  for f in ("factor_ids","blocker_ids"):
   raw=getattr(self,f)
   if not isinstance(raw,tuple):raise PriorityError(f"{f} must be typed tuple")
   limit=_MAX_FACTORS if f=="factor_ids" else _MAX_CONSTRAINTS
   if len(raw)>limit:raise PriorityError(f"{f} exceeds policy bound")
   vals=tuple(sorted(_id(v,f) for v in raw))
   if len(vals)!=len(set(vals)):raise PriorityError(f"{f} contains duplicate identities")
   object.__setattr__(self,f,vals)
  if self.blocked is not bool(self.blocker_ids):raise PriorityError("blocked must match blocker_ids")
  if not isinstance(self.input_digest,str) or not _SHA.fullmatch(self.input_digest):raise PriorityError("input_digest must be lowercase sha256")
 @property
 def digest(self):return _digest({"item_id":self.item_id,"blocked":self.blocked,"score":self.score,"effective_score":self.effective_score,"factor_ids":self.factor_ids,"blocker_ids":self.blocker_ids,"age_boost":self.age_boost,"input_digest":self.input_digest})

class PriorityEngine:
 def __init__(self,*,max_age_boost:float=5.0,age_step:float=.1,hysteresis:float=.25):
  for name,value in (("max_age_boost",max_age_boost),("age_step",age_step),("hysteresis",hysteresis)):
   if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):raise PriorityError(f"{name} must be finite numeric")
  if not 0<=max_age_boost<=10 or not 0<=age_step<=1 or not 0<=hysteresis<=5:raise PriorityError("engine bounds invalid")
  self.max_age_boost=max_age_boost;self.age_step=age_step;self.hysteresis=hysteresis
 def decide(self,item_id:str,inputs, constraints=(),*,age_epochs:int=0,previous_score:float|None=None)->PriorityDecision:
  _id(item_id,"item_id")
  if not isinstance(inputs,tuple) or any(not isinstance(x,PriorityInput) for x in inputs):raise PriorityError("inputs must be typed tuple")
  if not isinstance(constraints,tuple) or any(not isinstance(x,PriorityConstraint) for x in constraints):raise PriorityError("constraints must be typed tuple")
  if len(inputs)>_MAX_FACTORS or len(constraints)>_MAX_CONSTRAINTS:raise PriorityError("priority input cardinality exceeds policy bound")
  factors=tuple(sorted(inputs,key=lambda x:x.factor_id))
  constraint_set=tuple(sorted(constraints,key=lambda x:x.constraint_id))
  if len({f.factor_id for f in factors})!=len(factors):raise PriorityError("duplicate priority factor")
  if len({x.constraint_id for x in constraint_set})!=len(constraint_set):raise PriorityError("duplicate priority constraint")
  blockers=tuple(x.constraint_id for x in constraint_set if x.kind is ConstraintKind.HARD_BLOCKER and x.active)
  if not isinstance(age_epochs,int) or isinstance(age_epochs,bool) or age_epochs<0:raise PriorityError("age_epochs must be non-negative integer")
  if previous_score is not None and (not isinstance(previous_score,(int,float)) or isinstance(previous_score,bool) or not math.isfinite(previous_score)):raise PriorityError("previous_score must be finite numeric")
  raw=sum(f.contribution for f in factors)
  age=min(self.max_age_boost,age_epochs*self.age_step)
  target=raw+age
  effective=target
  if previous_score is not None and abs(target-previous_score)<self.hysteresis:effective=previous_score
  input_digest=_digest({"item_id":item_id,"factors":[{"factor_id":f.factor_id,"provenance_ref":f.provenance_ref,"value":f.value,"weight":f.weight} for f in factors],"constraints":[{"constraint_id":x.constraint_id,"kind":x.kind.value,"active":x.active,"provenance_ref":x.provenance_ref,"reason":x.reason.strip()} for x in constraint_set],"age_epochs":age_epochs,"previous_score":previous_score,"engine":{"max_age_boost":self.max_age_boost,"age_step":self.age_step,"hysteresis":self.hysteresis}})
  return PriorityDecision(item_id,bool(blockers),round(raw,8),round(effective,8),tuple(f.factor_id for f in factors),blockers,round(age,8),input_digest)
 def rank(self,decisions):
  if not isinstance(decisions,tuple) or any(not isinstance(d,PriorityDecision) for d in decisions):raise PriorityError("decisions must be typed tuple")
  if len(decisions)>4096:raise PriorityError("decision set exceeds policy bound")
  items=decisions
  if len({d.item_id for d in items})!=len(items):raise PriorityError("duplicate decision item")
  return tuple(sorted(items,key=lambda d:(d.blocked,-d.effective_score,d.item_id)))
