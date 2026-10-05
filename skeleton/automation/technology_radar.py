"""Evidence-gated technology radar for VOL-114."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class RadarError(ValueError):pass
class RadarState(str,Enum): CANDIDATE="candidate"; EXPERIMENT="experiment"; ADOPTED="adopted"; RETIRED="retired"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise RadarError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class TechnologyExitCriteria:
 max_cost:int;max_risk:int;decision_tick:int
 def __post_init__(self):
  for f in ("max_cost","max_risk","decision_tick"):\n   v=getattr(self,f)\n   if not isinstance(v,int) or isinstance(v,bool) or v<0:raise RadarError("exit criteria must be nonnegative integers")
@dataclass(frozen=True,slots=True)
class TechnologyCandidate:
 technology_id:str;purpose:str;baseline_id:str;owner_id:str;budget:int;decision_tick:int;exit:TechnologyExitCriteria
 def __post_init__(self):
  for f in ("technology_id","baseline_id","owner_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  if not isinstance(self.purpose,str) or not self.purpose.strip():raise RadarError("purpose budget and horizon required")\n  if not isinstance(self.budget,int) or isinstance(self.budget,bool) or self.budget<1 or not isinstance(self.decision_tick,int) or isinstance(self.decision_tick,bool) or self.decision_tick<1:raise RadarError("purpose budget and horizon required")\n  if not isinstance(self.exit,TechnologyExitCriteria):raise RadarError("exit criteria required")\n  if self.exit.decision_tick!=self.decision_tick:raise RadarError("candidate and exit decision horizons must match")\n  if self.budget>self.exit.max_cost:raise RadarError("candidate budget exceeds exit cost criterion")
@dataclass(frozen=True,slots=True)
class RadarDecision:
 technology_id:str;state:RadarState;evidence_ids:tuple[str,...];architecture_decision_id:str|None=None
 def __post_init__(self):
  object.__setattr__(self,"technology_id",_id(self.technology_id,"technology_id"))
  if not isinstance(self.state,RadarState):raise RadarError("state must be RadarState")\n  if not isinstance(self.evidence_ids,tuple):raise RadarError("evidence_ids must be tuple")\n  for x in self.evidence_ids:_id(x,"evidence_id")\n  if len(set(self.evidence_ids))!=len(self.evidence_ids):raise RadarError("duplicate decision evidence")
  if self.architecture_decision_id is not None:object.__setattr__(self,"architecture_decision_id",_id(self.architecture_decision_id,"architecture_decision_id"))
  if self.state is RadarState.ADOPTED and (not self.evidence_ids or self.architecture_decision_id is None):raise RadarError("adoption requires evidence and architecture decision")
class TechnologyRadar:
 def __init__(self,candidates):self.candidates={x.technology_id:x for x in candidates};self.states={x.technology_id:RadarState.CANDIDATE for x in candidates}
 def decide(self,decision,current_tick):
  c=self.candidates.get(decision.technology_id)
  if c is None:raise RadarError("unknown technology")
  if current_tick>c.decision_tick and decision.state not in (RadarState.RETIRED,):raise RadarError("decision horizon expired")
  prior=self.states[c.technology_id]
  allowed={RadarState.CANDIDATE:{RadarState.EXPERIMENT,RadarState.RETIRED},RadarState.EXPERIMENT:{RadarState.ADOPTED,RadarState.RETIRED},RadarState.ADOPTED:{RadarState.RETIRED},RadarState.RETIRED:set()}
  if decision.state not in allowed[prior]:raise RadarError("invalid radar transition")
  self.states[c.technology_id]=decision.state;return decision.state
