from dataclasses import dataclass
@dataclass(frozen=True)
class ReasoningStage: stage_id:str; strategy:str; model:str; version:str
@dataclass(frozen=True)
class ReasoningCost: units:float; currency:str
@dataclass(frozen=True)
class CostAttribution: operation_id:str; stage:ReasoningStage; cost:ReasoningCost
def attribute(operation_id,stage,units,currency="compute"):
 if units<0:raise ValueError("negative cost")
 return CostAttribution(operation_id,stage,ReasoningCost(units,currency))
def report(rows):return sum(x.cost.units for x in rows)
