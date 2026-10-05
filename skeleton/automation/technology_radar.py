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
  if min(self.max_cost,self.max_risk,self.decision_tick)<0:raise RadarError("exit criteria must be nonnegative")
@dataclass(frozen=True,slots=True)
class TechnologyCandidate:
 technology_id:str;purpose:str;baseline_id:str;owner_id:str;budget:int;decision_tick:int;exit:TechnologyExitCriteria
 def __post_init__(self):
  for f in ("technology_id","baseline_id","owner_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  if not self.purpose.strip() or self.budget<1 or self.decision_tick<1:raise RadarError("purpose budget and horizon required")
@dataclass(frozen=True,slots=True)
class RadarDecision:
 technology_id:str;state:RadarState;evidence_ids:tuple[str,...];architecture_decision_id:str|None=None
 def __post_init__(self):
  object.__setattr__(self,"technology_id",_id(self.technology_id,"technology_id"))
  for x in self.evidence_ids:_id(x,"evidence_id")
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
