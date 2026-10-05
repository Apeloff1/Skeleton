from dataclasses import dataclass
@dataclass(frozen=True)
class StrategyConstraint: allowed:tuple[str,...]; max_cost:float
@dataclass(frozen=True)
class StrategySelection: name:str; estimated_cost:float; score:float
@dataclass(frozen=True)
class StrategyDecision: selected:StrategySelection|None; abstained:bool; reason:str
def select(c,candidates):
 valid=[x for x in candidates if x.name in c.allowed and x.estimated_cost<=c.max_cost]
 if not valid:return StrategyDecision(None,True,"no strategy satisfies constraints")
 valid.sort(key=lambda x:(-x.score,x.estimated_cost,x.name));return StrategyDecision(valid[0],False,"eligible")
