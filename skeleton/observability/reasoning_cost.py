from dataclasses import dataclass
import math
@dataclass(frozen=True)
class ReasoningStage: stage_id:str; strategy:str; model:str; version:str
@dataclass(frozen=True)
class ReasoningCost: units:float; currency:str
@dataclass(frozen=True)
class CostAttribution: operation_id:str; stage:ReasoningStage; cost:ReasoningCost
def attribute(operation_id,stage,units,currency="compute"):
 if isinstance(units,bool) or not isinstance(units,(int,float)) or not math.isfinite(units) or units<0:raise ValueError("invalid cost")
 if not operation_id or not stage.stage_id or not currency:raise ValueError("cost attribution identity required")
 return CostAttribution(operation_id,stage,ReasoningCost(units,currency))
def report(rows):
 xs=tuple(rows);keys=[(x.operation_id,x.stage.stage_id) for x in xs]
 if len(keys)!=len(set(keys)):raise ValueError("duplicate cost attribution")
 return sum(x.cost.units for x in xs)
