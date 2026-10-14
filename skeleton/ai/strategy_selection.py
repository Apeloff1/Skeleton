from dataclasses import dataclass
import math
@dataclass(frozen=True)
class StrategyConstraint: allowed:tuple[str,...]; max_cost:float
@dataclass(frozen=True)
class StrategySelection: name:str; estimated_cost:float; score:float; production_eligible:bool=True
@dataclass(frozen=True)
class StrategyDecision: selected:StrategySelection|None; abstained:bool; reason:str
def _finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def select(c,candidates):
 candidates=tuple(candidates)
 if any(not x.name or not isinstance(x.production_eligible,bool) for x in candidates):raise ValueError("valid strategy candidates required")
 if len([x.name for x in candidates])!=len(set(x.name for x in candidates)):raise ValueError("duplicate strategy candidate")
 if not _finite(c.max_cost) or c.max_cost<0 or len(c.allowed)!=len(set(c.allowed)):raise ValueError("invalid strategy constraint")
 valid=[x for x in candidates if x.production_eligible and x.name in c.allowed and _finite(x.estimated_cost) and _finite(x.score) and x.estimated_cost>=0 and x.estimated_cost<=c.max_cost]
 if not valid:return StrategyDecision(None,True,"no production-eligible strategy satisfies constraints")
 valid.sort(key=lambda x:(-x.score,x.estimated_cost,x.name));return StrategyDecision(valid[0],False,"eligible")
