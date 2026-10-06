"""Deterministic reasoning budget admission layered on canonical cost attribution."""
from dataclasses import dataclass
from skeleton.observability.reasoning_cost import CostAttribution, report

@dataclass(frozen=True)
class ReasoningBudget:
 operation_id:str; currency:str; limit:float
 def __post_init__(self):
  if not self.operation_id or not self.currency or isinstance(self.limit,bool) or self.limit<0: raise ValueError("invalid reasoning budget")

def admit_reasoning(budget:ReasoningBudget, prior:tuple[CostAttribution,...], requested:CostAttribution)->float:
 if requested.operation_id!=budget.operation_id: raise PermissionError("cross-operation cost attribution")
 rows=tuple(prior)+(requested,)
 if any(r.operation_id!=budget.operation_id for r in rows): raise PermissionError("cross-operation cost attribution")
 if any(r.cost.currency!=budget.currency for r in rows): raise PermissionError("reasoning budget currency mismatch")
 total=report(rows)
 if total>budget.limit: raise PermissionError("reasoning budget exceeded")
 return total
